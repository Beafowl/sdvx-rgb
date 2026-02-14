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

        // Copy strip data to a local buffer and apply transforms
        uint8_t transformed[282]; // largest strip: ctrl_panel = 94 * 3 = 282
        int count = TapeLedDataCount[index];
        memcpy(transformed, data, count);
        TransformStrip(g_transformConfig.strips[index], transformed, count);

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