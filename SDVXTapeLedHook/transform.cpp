#include "transform.h"
#include <cmath>
#include <cstring>
#include <algorithm>

// How many hook calls between reload checks (~300 calls ≈ 3 seconds at 10 calls/frame * 60fps)
static constexpr int RELOAD_INTERVAL = 300;

const char* StripSectionNames[10] = {
    "title",
    "upper_left_speaker",
    "upper_right_speaker",
    "left_wing",
    "right_wing",
    "ctrl_panel",
    "lower_left_speaker",
    "lower_right_speaker",
    "woofer",
    "v_unit"
};

// Build a gamma lookup table for a given gamma value
static void BuildGammaLUT(uint8_t lut[256], float gamma) {
    if (gamma == 1.0f) {
        for (int i = 0; i < 256; i++)
            lut[i] = static_cast<uint8_t>(i);
    } else {
        float inv = 1.0f / gamma;
        for (int i = 0; i < 256; i++) {
            float normalized = static_cast<float>(i) / 255.0f;
            float corrected = powf(normalized, inv);
            int val = static_cast<int>(corrected * 255.0f + 0.5f);
            lut[i] = static_cast<uint8_t>(std::min(std::max(val, 0), 255));
        }
    }
}

// Parse a ChannelOrder from a string like "RGB", "GBR", etc.
static ChannelOrder ParseChannelOrder(const char* str) {
    if (_stricmp(str, "RBG") == 0) return CH_RBG;
    if (_stricmp(str, "GRB") == 0) return CH_GRB;
    if (_stricmp(str, "GBR") == 0) return CH_GBR;
    if (_stricmp(str, "BRG") == 0) return CH_BRG;
    if (_stricmp(str, "BGR") == 0) return CH_BGR;
    return CH_RGB;
}

// Parse a hex color string like "8000FF" or "#8000FF" into r, g, b. Returns true on success.
static bool ParseHexColor(const char* str, uint8_t& r, uint8_t& g, uint8_t& b) {
    if (!str || str[0] == '\0')
        return false;
    const char* hex = str;
    if (hex[0] == '#') hex++;
    if (strlen(hex) != 6)
        return false;
    unsigned int val;
    if (sscanf_s(hex, "%06x", &val) != 1)
        return false;
    r = static_cast<uint8_t>((val >> 16) & 0xFF);
    g = static_cast<uint8_t>((val >> 8) & 0xFF);
    b = static_cast<uint8_t>(val & 0xFF);
    return true;
}

// Read a float value from INI (GetPrivateProfileString then atof)
static float GetProfileFloat(const char* section, const char* key, float defaultVal, const char* path) {
    char buf[64];
    char defBuf[64];
    sprintf_s(defBuf, "%.4f", defaultVal);
    GetPrivateProfileStringA(section, key, defBuf, buf, sizeof(buf), path);
    return static_cast<float>(atof(buf));
}

// Load settings for one strip from a given INI section, with fallback defaults
static void LoadStripFromSection(StripTransform& strip, const char* section,
                                  const StripTransform& defaults, const char* path) {
    char orderStr[16];
    // Determine the default channel order string for GetPrivateProfileString fallback
    const char* defOrder = "RGB";
    switch (defaults.channelOrder) {
        case CH_RBG: defOrder = "RBG"; break;
        case CH_GRB: defOrder = "GRB"; break;
        case CH_GBR: defOrder = "GBR"; break;
        case CH_BRG: defOrder = "BRG"; break;
        case CH_BGR: defOrder = "BGR"; break;
        default: defOrder = "RGB"; break;
    }

    GetPrivateProfileStringA(section, "channel_order", defOrder, orderStr, sizeof(orderStr), path);
    strip.channelOrder = ParseChannelOrder(orderStr);

    strip.gamma_r = GetProfileFloat(section, "gamma_r", defaults.gamma_r, path);
    strip.gamma_g = GetProfileFloat(section, "gamma_g", defaults.gamma_g, path);
    strip.gamma_b = GetProfileFloat(section, "gamma_b", defaults.gamma_b, path);

    strip.hue_shift = GetPrivateProfileIntA(section, "hue_shift", defaults.hue_shift, path);
    strip.saturation = GetPrivateProfileIntA(section, "saturation", defaults.saturation, path);
    strip.brightness = GetPrivateProfileIntA(section, "brightness", defaults.brightness, path);

    // Clamp values
    strip.hue_shift = ((strip.hue_shift % 360) + 360) % 360;
    strip.saturation = std::min(std::max(strip.saturation, 0), 200);
    strip.brightness = std::min(std::max(strip.brightness, 0), 200);

    // Parse static_color (hex RGB like "8000FF" or "#8000FF")
    char colorStr[16];
    GetPrivateProfileStringA(section, "static_color", "", colorStr, sizeof(colorStr), path);
    if (ParseHexColor(colorStr, strip.static_r, strip.static_g, strip.static_b)) {
        strip.static_color_enabled = true;
    } else {
        strip.static_color_enabled = defaults.static_color_enabled;
        strip.static_r = defaults.static_r;
        strip.static_g = defaults.static_g;
        strip.static_b = defaults.static_b;
    }

    // Parse gradient_color (second color for gradient; requires static_color to be set)
    char gradStr[16];
    GetPrivateProfileStringA(section, "gradient_color", "", gradStr, sizeof(gradStr), path);
    if (strip.static_color_enabled && ParseHexColor(gradStr, strip.gradient_r2, strip.gradient_g2, strip.gradient_b2)) {
        strip.gradient_enabled = true;
    } else {
        strip.gradient_enabled = defaults.gradient_enabled;
        strip.gradient_r2 = defaults.gradient_r2;
        strip.gradient_g2 = defaults.gradient_g2;
        strip.gradient_b2 = defaults.gradient_b2;
    }

    // Build gamma LUTs
    BuildGammaLUT(strip.lut_r, strip.gamma_r);
    BuildGammaLUT(strip.lut_g, strip.gamma_g);
    BuildGammaLUT(strip.lut_b, strip.gamma_b);

    // Determine if any transform is actually active
    strip.enabled = (strip.channelOrder != CH_RGB ||
                     strip.gamma_r != 1.0f ||
                     strip.gamma_g != 1.0f ||
                     strip.gamma_b != 1.0f ||
                     strip.hue_shift != 0 ||
                     strip.saturation != 100 ||
                     strip.brightness != 100 ||
                     strip.static_color_enabled ||
                     strip.gradient_enabled);
}

void InitConfig(TransformConfig& config, HMODULE hModule) {
    memset(&config, 0, sizeof(config));

    // Resolve INI path: same directory as the DLL
    wchar_t dllPath[MAX_PATH];
    GetModuleFileNameW(hModule, dllPath, MAX_PATH);
    // Find last backslash and replace filename
    wchar_t* lastSlash = wcsrchr(dllPath, L'\\');
    if (lastSlash) {
        *(lastSlash + 1) = L'\0';
    }
    wcscpy_s(config.iniPath, dllPath);
    wcscat_s(config.iniPath, L"sdvxrgb.ini");

    config.callCounter = 0;
    config.lastWriteTime = {};

    // Set identity defaults for all strips
    for (int i = 0; i < 10; i++) {
        config.strips[i].enabled = false;
        config.strips[i].channelOrder = CH_RGB;
        config.strips[i].gamma_r = 1.0f;
        config.strips[i].gamma_g = 1.0f;
        config.strips[i].gamma_b = 1.0f;
        config.strips[i].hue_shift = 0;
        config.strips[i].saturation = 100;
        config.strips[i].brightness = 100;
        config.strips[i].static_color_enabled = false;
        config.strips[i].static_r = 0;
        config.strips[i].static_g = 0;
        config.strips[i].static_b = 0;
        config.strips[i].gradient_enabled = false;
        config.strips[i].gradient_r2 = 0;
        config.strips[i].gradient_g2 = 0;
        config.strips[i].gradient_b2 = 0;
        BuildGammaLUT(config.strips[i].lut_r, 1.0f);
        BuildGammaLUT(config.strips[i].lut_g, 1.0f);
        BuildGammaLUT(config.strips[i].lut_b, 1.0f);
    }
}

void LoadConfig(TransformConfig& config) {
    // Convert wide path to ANSI for GetPrivateProfileIntA/StringA
    char iniPathA[MAX_PATH];
    WideCharToMultiByte(CP_ACP, 0, config.iniPath, -1, iniPathA, MAX_PATH, nullptr, nullptr);

    // Check if file exists
    DWORD attr = GetFileAttributesW(config.iniPath);
    if (attr == INVALID_FILE_ATTRIBUTES) {
        // No config file — all strips stay at identity defaults
        for (int i = 0; i < 10; i++) {
            config.strips[i].enabled = false;
        }
        return;
    }

    // Update last write time
    HANDLE hFile = CreateFileW(config.iniPath, GENERIC_READ, FILE_SHARE_READ,
                               nullptr, OPEN_EXISTING, 0, nullptr);
    if (hFile != INVALID_HANDLE_VALUE) {
        GetFileTime(hFile, nullptr, nullptr, &config.lastWriteTime);
        CloseHandle(hFile);
    }

    // Load [global] defaults first
    StripTransform globalDefaults;
    globalDefaults.channelOrder = CH_RGB;
    globalDefaults.gamma_r = 1.0f;
    globalDefaults.gamma_g = 1.0f;
    globalDefaults.gamma_b = 1.0f;
    globalDefaults.hue_shift = 0;
    globalDefaults.saturation = 100;
    globalDefaults.brightness = 100;
    globalDefaults.static_color_enabled = false;
    globalDefaults.static_r = 0;
    globalDefaults.static_g = 0;
    globalDefaults.static_b = 0;
    globalDefaults.gradient_enabled = false;
    globalDefaults.gradient_r2 = 0;
    globalDefaults.gradient_g2 = 0;
    globalDefaults.gradient_b2 = 0;
    LoadStripFromSection(globalDefaults, "global", globalDefaults, iniPathA);

    // Load per-strip settings, falling back to [global] values
    for (int i = 0; i < 10; i++) {
        LoadStripFromSection(config.strips[i], StripSectionNames[i], globalDefaults, iniPathA);
    }
}

void CheckReload(TransformConfig& config) {
    config.callCounter++;
    if (config.callCounter < RELOAD_INTERVAL)
        return;
    config.callCounter = 0;

    // Check if file's write time changed
    HANDLE hFile = CreateFileW(config.iniPath, GENERIC_READ, FILE_SHARE_READ,
                               nullptr, OPEN_EXISTING, 0, nullptr);
    if (hFile == INVALID_HANDLE_VALUE) {
        // File might have been deleted — reset to identity
        if (config.lastWriteTime.dwHighDateTime != 0 || config.lastWriteTime.dwLowDateTime != 0) {
            config.lastWriteTime = {};
            for (int i = 0; i < 10; i++) {
                config.strips[i].enabled = false;
                config.strips[i].channelOrder = CH_RGB;
                config.strips[i].gamma_r = 1.0f;
                config.strips[i].gamma_g = 1.0f;
                config.strips[i].gamma_b = 1.0f;
                config.strips[i].hue_shift = 0;
                config.strips[i].saturation = 100;
                config.strips[i].brightness = 100;
                config.strips[i].static_color_enabled = false;
                config.strips[i].static_r = 0;
                config.strips[i].static_g = 0;
                config.strips[i].static_b = 0;
                config.strips[i].gradient_enabled = false;
                config.strips[i].gradient_r2 = 0;
                config.strips[i].gradient_g2 = 0;
                config.strips[i].gradient_b2 = 0;
                BuildGammaLUT(config.strips[i].lut_r, 1.0f);
                BuildGammaLUT(config.strips[i].lut_g, 1.0f);
                BuildGammaLUT(config.strips[i].lut_b, 1.0f);
            }
        }
        return;
    }

    FILETIME ft;
    GetFileTime(hFile, nullptr, nullptr, &ft);
    CloseHandle(hFile);

    if (CompareFileTime(&ft, &config.lastWriteTime) != 0) {
        LoadConfig(config);
    }
}

// --- RGB <-> HSV conversion (integer-friendly) ---

// Convert RGB (0-255) to HSV where H=0-359, S=0-255, V=0-255
static void RGBtoHSV(uint8_t r, uint8_t g, uint8_t b, int& h, int& s, int& v) {
    int maxVal = std::max({ (int)r, (int)g, (int)b });
    int minVal = std::min({ (int)r, (int)g, (int)b });
    int delta = maxVal - minVal;

    v = maxVal;

    if (maxVal == 0) {
        s = 0;
        h = 0;
        return;
    }

    s = (delta * 255) / maxVal;

    if (delta == 0) {
        h = 0;
        return;
    }

    if (maxVal == r) {
        h = 60 * (g - b) / delta;
    } else if (maxVal == g) {
        h = 120 + 60 * (b - r) / delta;
    } else {
        h = 240 + 60 * (r - g) / delta;
    }

    if (h < 0)
        h += 360;
}

// Convert HSV (H=0-359, S=0-255, V=0-255) back to RGB (0-255)
static void HSVtoRGB(int h, int s, int v, uint8_t& r, uint8_t& g, uint8_t& b) {
    if (s == 0) {
        r = g = b = static_cast<uint8_t>(v);
        return;
    }

    h = h % 360;
    int region = h / 60;
    int remainder = h % 60;

    int p = (v * (255 - s)) / 255;
    int q = (v * (255 - (s * remainder) / 60)) / 255;
    int t = (v * (255 - (s * (60 - remainder)) / 60)) / 255;

    switch (region) {
        case 0: r = (uint8_t)v; g = (uint8_t)t; b = (uint8_t)p; break;
        case 1: r = (uint8_t)q; g = (uint8_t)v; b = (uint8_t)p; break;
        case 2: r = (uint8_t)p; g = (uint8_t)v; b = (uint8_t)t; break;
        case 3: r = (uint8_t)p; g = (uint8_t)q; b = (uint8_t)v; break;
        case 4: r = (uint8_t)t; g = (uint8_t)p; b = (uint8_t)v; break;
        default: r = (uint8_t)v; g = (uint8_t)p; b = (uint8_t)q; break;
    }
}

void TransformStrip(const StripTransform& strip, uint8_t* data, int numBytes) {
    if (!strip.enabled)
        return;

    bool needHSV = (strip.hue_shift != 0 || strip.saturation != 100);

    // Precompute static/gradient color's H and S if needed
    int staticH1 = 0, staticS1 = 0, staticV1 = 0;
    int staticH2 = 0, staticS2 = 0, staticV2 = 0;
    if (strip.static_color_enabled) {
        RGBtoHSV(strip.static_r, strip.static_g, strip.static_b, staticH1, staticS1, staticV1);
        if (strip.gradient_enabled) {
            RGBtoHSV(strip.gradient_r2, strip.gradient_g2, strip.gradient_b2, staticH2, staticS2, staticV2);
        }
    }

    int numLEDs = numBytes / 3;

    for (int i = 0; i < numBytes; i += 3) {
        uint8_t r = data[i];
        uint8_t g = data[i + 1];
        uint8_t b = data[i + 2];

        // swap the channels
        uint8_t cr, cg, cb;
        switch (strip.channelOrder) {
            case CH_RBG: cr = r; cg = b; cb = g; break;
            case CH_GRB: cr = g; cg = r; cb = b; break;
            case CH_GBR: cr = g; cg = b; cb = r; break;
            case CH_BRG: cr = b; cg = r; cb = g; break;
            case CH_BGR: cr = b; cg = g; cb = r; break;
            default:     cr = r; cg = g; cb = b; break;
        }

        // Step 2: Gamma correction (LUT)
        cr = strip.lut_r[cr];
        cg = strip.lut_g[cg];
        cb = strip.lut_b[cb];

        // Step 3: Static color / gradient OR hue shift/saturation
        if (strip.static_color_enabled) {
            int h, s, v;
            RGBtoHSV(cr, cg, cb, h, s, v);

            if (strip.gradient_enabled && numLEDs > 1) {
                // Interpolate H and S between color 1 and color 2 based on LED position
                int ledIdx = i / 3;
                // Take shortest path around the hue circle
                int hDiff = staticH2 - staticH1;
                if (hDiff > 180) hDiff -= 360;
                if (hDiff < -180) hDiff += 360;
                int interpH = (staticH1 + hDiff * ledIdx / (numLEDs - 1) + 360) % 360;
                int interpS = staticS1 + (staticS2 - staticS1) * ledIdx / (numLEDs - 1);
                HSVtoRGB(interpH, interpS, v, cr, cg, cb);
            } else {
                // Single static color
                HSVtoRGB(staticH1, staticS1, v, cr, cg, cb);
            }
        } else if (needHSV) {
            int h, s, v;
            RGBtoHSV(cr, cg, cb, h, s, v);

            h = (h + strip.hue_shift) % 360;

            if (strip.saturation != 100) {
                s = (s * strip.saturation) / 100;
                s = std::min(s, 255);
            }

            HSVtoRGB(h, s, v, cr, cg, cb);
        }

        // brightness scaling
        if (strip.brightness != 100) {
            int br = (cr * strip.brightness) / 100;
            int bg = (cg * strip.brightness) / 100;
            int bb = (cb * strip.brightness) / 100;
            cr = static_cast<uint8_t>(std::min(br, 255));
            cg = static_cast<uint8_t>(std::min(bg, 255));
            cb = static_cast<uint8_t>(std::min(bb, 255));
        }

        data[i] = cr;
        data[i + 1] = cg;
        data[i + 2] = cb;
    }
}
