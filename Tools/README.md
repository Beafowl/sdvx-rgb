# SDVX RGB Tools

Python utilities for working with SDVX RGB LED data. All tools use only the Python standard library — no `pip install` required.

## Tools

### sdvx_rgb_web.py

Web-based editor for `sdvxrgb.ini`. Runs a local HTTP server that serves a frontend for configuring LED strip transforms. The hook DLL hot-reloads the INI file automatically.

```
python sdvx_rgb_web.py [ini_path] [--host HOST] [--port PORT]
```

| Argument | Default | Description |
|---|---|---|
| `ini_path` | `../SDVXTapeLedHook/sdvxrgb.ini` | Path to the INI file |
| `--host` | `127.0.0.1` | Address to bind to |
| `--port` | `8274` | Port to listen on |

Open `http://localhost:8274` in a browser after starting.

#### Web API

##### `GET /api/config`

Returns the current INI configuration as JSON.

Response:

```json
{
  "strips": ["title", "upper_left_speaker", "..."],
  "keys": ["channel_order", "gamma_r", "..."],
  "config": {
    "global": { "brightness": "80" },
    "title": { "static_color": "FF00AA" }
  }
}
```

- `strips` — list of the 10 strip section names
- `keys` — list of recognized per-strip keys
- `config` — object of INI sections, each mapping keys to string values. Sections or keys not present in the INI file are omitted.

##### `POST /api/config`

Writes the full configuration to the INI file. The hook DLL detects the file change and hot-reloads it.

Request body:

```json
{
  "global": { "brightness": "80" },
  "title": { "static_color": "FF00AA", "gradient_color": "" }
}
```

Each top-level key is an INI section. Keys with empty string values are omitted from the file. Sections where all values are empty are omitted entirely.

Response:

```json
{ "ok": true }
```

On error (400):

```json
{ "error": "description" }
```

### sdvx_rgb_controller.py

Tkinter GUI for adjusting LED color transforms per strip. Reads shared memory for a live color preview and writes `sdvxrgb.ini` on every change.

```
python sdvx_rgb_controller.py [path_to_sdvxrgb.ini]
```

Requires the game to be running with the hook loaded for the live preview to work.

### sdvx_rgb_capture.py

Records LED data from shared memory for offline analysis and comparison between game versions.

```
python sdvx_rgb_capture.py record <output.sdvxcap>
python sdvx_rgb_capture.py dump <capture.sdvxcap>
python sdvx_rgb_capture.py compare <old.sdvxcap> <new.sdvxcap>
```

| Command | Description |
|---|---|
| `record` | Capture LED frames to a `.sdvxcap` file (Ctrl+C to stop) |
| `dump` | Print per-strip statistics (avg color, brightness, saturation, dominant hue) |
| `compare` | Diff two captures and suggest INI adjustments to match the old output |
