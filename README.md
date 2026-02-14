# sdvx-rgb

**Output SDVX tape LED data**

![rgb_effect](https://github.com/hlcm0/sdvx-rgb/assets/103294894/ddd0477e-8d16-472d-9812-67287682c630)

> Fork of [hlcm0/sdvx-rgb](https://github.com/hlcm0/sdvx-rgb) with added color transform support and configuration tools.

## What is this

A set of programs to display RGB effects of SDVX.

## It contains

1. **SDVXTapeLedHook.dll** — uses shared memory to expose raw tape LED data, with per-strip color transforms (hue shift, static color, gradient, gamma, brightness, saturation, channel reorder) configurable via `sdvxrgb.ini`.
2. **hid_send program** — reads from shared memory and sends data to an RP2040 via HID.
3. **RP2040 firmware** — drives WS2812 LED strips from GPIO0-9.
4. **Tools/** — Python utilities for configuring and inspecting LED data. See [Tools/README.md](Tools/README.md).

## sdvxrgb.ini

The hook DLL reads `sdvxrgb.ini` from the same directory as the DLL. It supports a `[global]` section (defaults for all strips) and per-strip sections. The file is hot-reloaded automatically.

### Supported keys

| Key | Type | Default | Description |
|---|---|---|---|
| `channel_order` | string | `RGB` | Channel reorder: `RGB`, `RBG`, `GRB`, `GBR`, `BRG`, `BGR` |
| `gamma_r` | float | `1.0` | Red gamma correction |
| `gamma_g` | float | `1.0` | Green gamma correction |
| `gamma_b` | float | `1.0` | Blue gamma correction |
| `hue_shift` | int | `0` | Hue rotation in degrees (0-359) |
| `saturation` | int | `100` | Saturation percentage (0-200, 100 = unchanged) |
| `brightness` | int | `100` | Brightness percentage (0-200, 100 = unchanged) |
| `static_color` | hex | | Override color (e.g. `FF00AA`), keeps original brightness |
| `gradient_color` | hex | | Second color for gradient (requires `static_color`) |

### Strip sections

`title`, `upper_left_speaker`, `upper_right_speaker`, `left_wing`, `right_wing`, `ctrl_panel`, `lower_left_speaker`, `lower_right_speaker`, `woofer`, `v_unit`

### Example

```ini
[global]
brightness=80

[title]
static_color=FE01E4

[left_wing]
static_color=0000FF
gradient_color=FF00FF
```

## How to use

1. Flash the firmware into RP2040 and connect the light strips to GPIO0-9 (defined in the firmware source file).
2. Connect the RP2040 to your PC and open `rgb_send.exe`.
3. Place `SDVXTapeLedHook.dll` (and optionally `sdvxrgb.ini`) into the same folder as `spice64.exe`.
4. Configure "Inject DLL Hooks" in spicecfg (only needed once).
5. Start the game using `spice64.exe` as normal.

## How to compile

### SDVXTapeLedHook.dll

1. Install MinHook static library with vcpkg:
```powershell
.\vcpkg install minhook:x64-windows-static
```
2. Open the project in Visual Studio 2022.
3. Add to project properties:
```
Configuration Properties -> VC++ Directories:
- Include Directories: Add $(VcpkgRoot)include
- Library Directories: Add $(VcpkgRoot)lib
```
4. Build the project.

### hid_send

Compile with Visual Studio 2022.

### RP2040 firmware

1. Install **Arduino IDE** and use [Earle Philhower's RP2040 core](https://github.com/earlephilhower/arduino-pico).
2. Choose TinyUSB as USB Stack, then upload the firmware.

## Credits

This project is a fork of [hlcm0/sdvx-rgb](https://github.com/hlcm0/sdvx-rgb). The original hook DLL, HID sender, RP2040 firmware, and visualizer were created by [hlcm0](https://github.com/hlcm0).

## References

- [spice2x](https://github.com/spice2x/spice2x.github.io)
- [hidapi](https://github.com/libusb/hidapi) for rgb_send
- [arduino-pico](https://github.com/earlephilhower/arduino-pico)
- [pico-sdk](https://github.com/raspberrypi/pico-sdk) for WS2812 PIO assembly code
- [Adafruit_TinyUSB_Arduino](https://github.com/adafruit/Adafruit_TinyUSB_Arduino)
- [HID](https://github.com/NicoHood/HID) for RawHID report descriptor
- [MinHook](https://github.com/TsudaKageyu/minhook)

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
