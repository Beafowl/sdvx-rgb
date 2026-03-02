#pragma once
#define NOMINMAX
#include <Windows.h>
#include <cstdint>

enum ChannelOrder {
    CH_RGB = 0,
    CH_RBG,
    CH_GRB,
    CH_GBR,
    CH_BRG,
    CH_BGR
};

struct StripTransform {
    bool enabled;               // false = skip transform (all identity)
    ChannelOrder channelOrder;
    float gamma_r, gamma_g, gamma_b;
    int hue_shift;              // 0-359 degrees
    int saturation;             // 0-200 percent (100 = no change)
    int brightness;             // 0-200 percent (100 = no change)
    int contrast;               // 0-200 percent (100 = no change, >100 = stronger pulse)
    bool static_color_enabled;  // true = override color (keeps brightness)
    uint8_t static_r, static_g, static_b;  // static color
    bool gradient_enabled;      // true = gradient between two colors (keeps brightness)
    uint8_t gradient_r2, gradient_g2, gradient_b2;  // gradient end color
    bool pulse_color_enabled;   // true = traveling pulse on beat
    uint8_t pulse_r, pulse_g, pulse_b;  // pulse color
    float pulse_speed;          // LEDs per second
    float pulse_width;          // half-width of solid center in LEDs
    float pulse_fade;           // fade length beyond solid center in LEDs
    float fade_in;              // fade-in duration in ms (0 = instant)
    float fade_out;             // fade-out duration in ms (0 = instant)
    uint8_t lut_r[256];        // precomputed gamma LUT
    uint8_t lut_g[256];
    uint8_t lut_b[256];
};

static constexpr int MAX_PULSES = 8;

struct PulseRender {
    int count;                  // number of active pulses (0 = none)
    float positions[MAX_PULSES]; // LED index (fractional) per pulse
    float width;                // half-width of solid center (shared)
    float fade;                 // fade length beyond solid center (shared)
    uint8_t r, g, b;           // pulse color (shared)
};

struct TransformConfig {
    StripTransform strips[10];
    wchar_t iniPath[MAX_PATH];
    FILETIME lastWriteTime;
    int callCounter;
};

// Strip section names in the INI file, indexed 0-9
extern const char* StripSectionNames[10];

// Initialize config with identity defaults and resolve INI path
void InitConfig(TransformConfig& config, HMODULE hModule);

// Load or reload config from INI file
void LoadConfig(TransformConfig& config);

// Check if INI file changed and reload if so (call every hook invocation)
void CheckReload(TransformConfig& config);

// Apply transformation to a strip's RGB data in-place
void TransformStrip(const StripTransform& strip, uint8_t* data, int numBytes,
                    const PulseRender& pulse = {});
