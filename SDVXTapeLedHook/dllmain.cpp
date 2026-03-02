#include <Windows.h>
#include <MinHook.h>
#include <cstdint>
#include "transform.h"

// shared memory
HANDLE hMapFile;
uint8_t* lpBase = nullptr;

// transform config (loaded from sdvxrgb.ini next to the DLL)
TransformConfig g_transformConfig;
HMODULE g_hModule = nullptr;

// Fade state for smooth LED activation/deactivation transitions
static constexpr int MAX_LEDS = 94; // largest strip: ctrl_panel = 94 LEDs
struct StripFadeState {
    float factor[MAX_LEDS];          // current fade factor per LED (0.0-1.0)
    uint8_t lastColor[MAX_LEDS * 3]; // last non-zero color (for fade-out)
    bool initialized;
    LARGE_INTEGER lastTime;
};

static StripFadeState g_fadeState[10] = {};

// Pulse state for beat-triggered traveling pulses (multiple per strip)
struct StripPulseState {
    bool seeded;                        // has prevBrightness been initialized?
    float prevBrightness;               // average brightness of previous frame
    LARGE_INTEGER lastTime;             // QPC timestamp of last update
    int pulseCount;                     // number of active pulses
    float positions[MAX_PULSES];        // position of each active pulse
};

static StripPulseState g_pulseState[10] = {};
static LARGE_INTEGER g_qpcFreq = {};
static constexpr float BEAT_THRESHOLD = 15.0f;

/*
* index mapping
*
* 0 - title - 222 bytes - 74 colors
* 1 - upper left speaker - 36 bytes - 12 colors
* 2 - upper right speaker - 36 bytes - 12 colors
* 3 - left wing - 168 bytes - 56 colors
* 4 - right wing - 168 bytes - 56 colors
* 5 - control panel - 282 bytes - 94 colors
* 6 - lower left speaker - 36 bytes - 12 colors
* 7 - lower right speaker - 36 bytes - 12 colors
* 8 - woofer - 42 bytes - 14 colors
* 9 - v unit - 258 bytes - 86 colors
*
* data is stored in RGB order, 3 bytes per color
*
*/

// Offset and count of each tape led data in shared memory
int TapeLedDataOffset[10] = { 0 * 3, 74 * 3, 86 * 3, 98 * 3, 154 * 3, 210 * 3, 304 * 3, 316 * 3, 328 * 3, 342 * 3 };
int TapeLedDataCount[10] = { 74 * 3, 12 * 3, 12 * 3, 56 * 3, 56 * 3, 94 * 3, 12 * 3, 12 * 3, 14 * 3, 86 * 3 };

// Define original function
typedef void(__fastcall* SetTapeLedData_t)(void* This, unsigned int index, uint8_t* data);

// Save original function pointer
SetTapeLedData_t fpOriginal = nullptr;

// Hook function
void __fastcall SetTapeLedDataHook(void* This, unsigned int index, uint8_t* data) {
    if (index < 10) {
        // Check for config hot-reload
        CheckReload(g_transformConfig);

        const StripTransform& strip = g_transformConfig.strips[index];
        int count = TapeLedDataCount[index];
        int numLEDs = count / 3;

        // Beat detection and pulse update
        PulseRender pulse = {};
        if (strip.pulse_color_enabled) {
            StripPulseState& ps = g_pulseState[index];

            // Compute average brightness of raw incoming data
            int sum = 0;
            for (int i = 0; i < count; i++)
                sum += data[i];
            float avgBrightness = static_cast<float>(sum) / static_cast<float>(count);

            LARGE_INTEGER now;
            QueryPerformanceCounter(&now);

            if (!ps.seeded) {
                // First call — seed brightness, don't trigger
                ps.prevBrightness = avgBrightness;
                ps.lastTime = now;
                ps.seeded = true;
            } else {
                // Compute elapsed time
                float elapsed = static_cast<float>(now.QuadPart - ps.lastTime.QuadPart)
                              / static_cast<float>(g_qpcFreq.QuadPart);
                if (elapsed > 0.1f) elapsed = 0.1f; // clamp to 100ms
                ps.lastTime = now;

                // Advance all active pulses and remove finished ones
                float limit = static_cast<float>(numLEDs);
                int write = 0;
                for (int j = 0; j < ps.pulseCount; j++) {
                    ps.positions[j] += strip.pulse_speed * elapsed;
                    if (ps.positions[j] < limit) {
                        ps.positions[write++] = ps.positions[j];
                    }
                }
                ps.pulseCount = write;

                // Check for beat: brightness rising above threshold
                float delta = avgBrightness - ps.prevBrightness;
                if (delta > BEAT_THRESHOLD && ps.pulseCount < MAX_PULSES) {
                    ps.positions[ps.pulseCount++] = 0.0f;
                }

                ps.prevBrightness = avgBrightness;
            }

            // Build render info
            if (ps.pulseCount > 0) {
                pulse.count = ps.pulseCount;
                for (int j = 0; j < ps.pulseCount; j++)
                    pulse.positions[j] = ps.positions[j];
                pulse.width = strip.pulse_width;
                pulse.fade = strip.pulse_fade;
                pulse.r = strip.pulse_r;
                pulse.g = strip.pulse_g;
                pulse.b = strip.pulse_b;
            }
        }

        // Copy strip data to a local buffer and apply transforms
        uint8_t transformed[282]; // largest strip: ctrl_panel = 94 * 3 = 282
        memcpy(transformed, data, count);
        TransformStrip(strip, transformed, count, pulse);

        // Apply fade in/out if configured
        if (strip.fade_in > 0.0f || strip.fade_out > 0.0f) {
            StripFadeState& fs = g_fadeState[index];

            LARGE_INTEGER now;
            QueryPerformanceCounter(&now);

            if (!fs.initialized) {
                // First call — initialize all factors based on current state
                for (int i = 0; i < numLEDs; i++) {
                    int idx = i * 3;
                    bool active = (transformed[idx] | transformed[idx + 1] | transformed[idx + 2]) != 0;
                    fs.factor[i] = active ? 1.0f : 0.0f;
                    fs.lastColor[idx] = transformed[idx];
                    fs.lastColor[idx + 1] = transformed[idx + 1];
                    fs.lastColor[idx + 2] = transformed[idx + 2];
                }
                fs.lastTime = now;
                fs.initialized = true;
            } else {
                float elapsed = static_cast<float>(now.QuadPart - fs.lastTime.QuadPart)
                              / static_cast<float>(g_qpcFreq.QuadPart);
                if (elapsed > 0.1f) elapsed = 0.1f; // clamp to 100ms
                fs.lastTime = now;

                for (int i = 0; i < numLEDs; i++) {
                    int idx = i * 3;
                    bool active = (transformed[idx] | transformed[idx + 1] | transformed[idx + 2]) != 0;

                    if (active) {
                        // Save the current color for potential future fade-out
                        fs.lastColor[idx] = transformed[idx];
                        fs.lastColor[idx + 1] = transformed[idx + 1];
                        fs.lastColor[idx + 2] = transformed[idx + 2];

                        // Ramp factor toward 1.0
                        if (strip.fade_in > 0.0f && fs.factor[i] < 1.0f) {
                            fs.factor[i] += (elapsed * 1000.0f) / strip.fade_in;
                            if (fs.factor[i] > 1.0f) fs.factor[i] = 1.0f;
                        } else {
                            fs.factor[i] = 1.0f;
                        }

                        // Apply fade factor to the transformed color
                        transformed[idx]     = static_cast<uint8_t>(transformed[idx]     * fs.factor[i]);
                        transformed[idx + 1] = static_cast<uint8_t>(transformed[idx + 1] * fs.factor[i]);
                        transformed[idx + 2] = static_cast<uint8_t>(transformed[idx + 2] * fs.factor[i]);
                    } else {
                        // Ramp factor toward 0.0
                        if (strip.fade_out > 0.0f && fs.factor[i] > 0.0f) {
                            fs.factor[i] -= (elapsed * 1000.0f) / strip.fade_out;
                            if (fs.factor[i] < 0.0f) fs.factor[i] = 0.0f;
                        } else {
                            fs.factor[i] = 0.0f;
                        }

                        // Output last known color scaled by fade factor
                        transformed[idx]     = static_cast<uint8_t>(fs.lastColor[idx]     * fs.factor[i]);
                        transformed[idx + 1] = static_cast<uint8_t>(fs.lastColor[idx + 1] * fs.factor[i]);
                        transformed[idx + 2] = static_cast<uint8_t>(fs.lastColor[idx + 2] * fs.factor[i]);
                    }
                }
            }
        }

        // Write transformed data to shared memory
        if (lpBase) {
            memcpy(lpBase + TapeLedDataOffset[index], transformed, count);
        }

        // Pass transformed data to original function
        fpOriginal(This, index, transformed);
        return;
    }

    // Index out of range — pass through unchanged
    fpOriginal(This, index, data);
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID lpReserved) {
    switch (reason) {
    case DLL_PROCESS_ATTACH: {
        g_hModule = hModule;

        // Init MinHook
        if (MH_Initialize() != MH_OK) {
            return FALSE;
        }

        // Get target module address
        HMODULE hTarget = GetModuleHandleA("libaio-iob2_video.dll");
        if (!hTarget) {
            return FALSE;
        }

        // Get target function address
        void* pTarget = GetProcAddress(hTarget,
            "?SetTapeLedData@AIO_IOB2_BI2X_UFC@@QEAAXIPEBX@Z");
        if (!pTarget) {
            return FALSE;
        }

        // Create Hook
        if (MH_CreateHook(pTarget, &SetTapeLedDataHook,
            reinterpret_cast<void**>(&fpOriginal)) != MH_OK) {
            return FALSE;
        }

        // Enable Hook
        if (MH_EnableHook(pTarget) != MH_OK) {
            return FALSE;
        }

        // Init shared memory
        hMapFile = CreateFileMapping(
            INVALID_HANDLE_VALUE,
            NULL,
            PAGE_READWRITE,
            0,
            1284,   // buffer size
            L"sdvxrgb"
        );
        if (hMapFile) {
            lpBase = static_cast<uint8_t*>(MapViewOfFile(
                hMapFile,
                FILE_MAP_ALL_ACCESS,
                0,
                0,
                1284   // buffer size
            ));
        }

        // Init transform config from sdvxrgb.ini
        InitConfig(g_transformConfig, hModule);
        LoadConfig(g_transformConfig);

        // Init QPC frequency for pulse timing
        QueryPerformanceFrequency(&g_qpcFreq);

        break;
    }
    case DLL_PROCESS_DETACH: {
        // Clean up shared memory
        if (lpBase) {
            UnmapViewOfFile(lpBase);
            lpBase = nullptr;
        }
        if (hMapFile) {
            CloseHandle(hMapFile);
            hMapFile = NULL;
        }

        // Clean up Hook
        MH_DisableHook(MH_ALL_HOOKS);
        MH_Uninitialize();
        break;
    }
    }
    return TRUE;
}