"""
SDVX RGB Web API

Minimal web API + frontend for editing sdvxrgb.ini.
Uses only the Python standard library (no Flask/etc).

Usage:
    python sdvx_rgb_web.py [--ini PATH] [--host HOST] [--port PORT]

Then open http://localhost:8274 in a browser.
"""

import argparse
import configparser
import filecmp
import json
import os
import re
import shutil
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

STRIP_NAMES = [
    "title",
    "upper_left_speaker",
    "upper_right_speaker",
    "left_wing",
    "right_wing",
    "ctrl_panel",
    "lower_left_speaker",
    "lower_right_speaker",
    "woofer",
    "v_unit",
]

STRIP_KEYS = [
    "channel_order",
    "gamma_r",
    "gamma_g",
    "gamma_b",
    "hue_shift",
    "saturation",
    "brightness",
    "static_color",
    "gradient_color",
]

INI_PATH = ""
PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")
CURRENT_PROFILE = None
FRONTEND_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "sdvx_rgb_web.html"
)


def read_ini():
    """Read sdvxrgb.ini and return a dict of sections."""
    config = configparser.ConfigParser()
    config.optionxform = str  # preserve case
    if os.path.exists(INI_PATH):
        config.read(INI_PATH, encoding="utf-8")

    result = {}
    for section in config.sections():
        result[section] = dict(config[section])
    return result


def write_ini(data):
    """Write a dict of sections to sdvxrgb.ini."""
    lines = []
    for section, values in data.items():
        # Only write sections that have at least one non-empty value
        non_empty = {k: v for k, v in values.items() if v != ""}
        if not non_empty:
            continue
        lines.append(f"[{section}]")
        for key, value in non_empty.items():
            lines.append(f"{key}={value}")
        lines.append("")
    with open(INI_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _valid_profile_name(name):
    """Check that profile name is safe for use as a filename."""
    return bool(name) and bool(re.match(r"^[A-Za-z0-9 _\-]+$", name))


def _profile_path(name):
    return os.path.join(PROFILES_DIR, name + ".ini")


def list_profiles():
    """Return sorted list of profile names (without .ini extension)."""
    os.makedirs(PROFILES_DIR, exist_ok=True)
    profiles = []
    for f in os.listdir(PROFILES_DIR):
        if f.lower().endswith(".ini"):
            profiles.append(f[:-4])
    profiles.sort(key=str.lower)
    return profiles


def save_profile(name):
    """Save the current INI file as a profile."""
    os.makedirs(PROFILES_DIR, exist_ok=True)
    shutil.copy2(INI_PATH, _profile_path(name))


def load_profile(name):
    """Load a profile into the current INI file."""
    global CURRENT_PROFILE
    src = _profile_path(name)
    if not os.path.exists(src):
        raise FileNotFoundError(f"Profile '{name}' not found")
    shutil.copy2(src, INI_PATH)
    CURRENT_PROFILE = name


def delete_profile(name):
    """Delete a saved profile."""
    global CURRENT_PROFILE
    path = _profile_path(name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Profile '{name}' not found")
    os.remove(path)
    if CURRENT_PROFILE == name:
        CURRENT_PROFILE = None


def detect_current_profile():
    """Set CURRENT_PROFILE by matching INI_PATH contents against saved profiles."""
    global CURRENT_PROFILE
    if not os.path.exists(INI_PATH):
        return
    for name in list_profiles():
        if filecmp.cmp(INI_PATH, _profile_path(name), shallow=False):
            CURRENT_PROFILE = name
            return


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Quiet logging — single line
        print(f"[{self.log_date_time_string()}] {args[0]}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            try:
                with open(FRONTEND_PATH, "r", encoding="utf-8") as f:
                    self._html_response(f.read())
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Frontend file not found")
            return

        if path == "/api/config":
            self._json_response(
                {
                    "strips": STRIP_NAMES,
                    "keys": STRIP_KEYS,
                    "config": read_ini(),
                    "profiles": list_profiles(),
                    "current_profile": CURRENT_PROFILE,
                }
            )
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/config":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                write_ini(data)
                self._json_response({"ok": True})
            except (json.JSONDecodeError, TypeError) as e:
                self._json_response({"error": str(e)}, status=400)
            return

        if path == "/api/profiles/save":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                name = data.get("name", "").strip()
                if not _valid_profile_name(name):
                    self._json_response(
                        {
                            "error": "Invalid profile name. Use only letters, numbers, spaces, hyphens, and underscores."
                        },
                        status=400,
                    )
                    return
                save_profile(name)
                global CURRENT_PROFILE
                CURRENT_PROFILE = name
                self._json_response(
                    {
                        "ok": True,
                        "profiles": list_profiles(),
                        "current_profile": CURRENT_PROFILE,
                    }
                )
            except (json.JSONDecodeError, TypeError) as e:
                self._json_response({"error": str(e)}, status=400)
            return

        if path == "/api/profiles/load":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                name = data.get("name", "").strip()
                load_profile(name)
                self._json_response(
                    {
                        "ok": True,
                        "config": read_ini(),
                        "current_profile": CURRENT_PROFILE,
                    }
                )
            except FileNotFoundError as e:
                self._json_response({"error": str(e)}, status=404)
            except (json.JSONDecodeError, TypeError) as e:
                self._json_response({"error": str(e)}, status=400)
            return

        if path == "/api/profiles/delete":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                name = data.get("name", "").strip()
                delete_profile(name)
                self._json_response(
                    {
                        "ok": True,
                        "profiles": list_profiles(),
                        "current_profile": CURRENT_PROFILE,
                    }
                )
            except FileNotFoundError as e:
                self._json_response({"error": str(e)}, status=404)
            except (json.JSONDecodeError, TypeError) as e:
                self._json_response({"error": str(e)}, status=400)
            return

        self.send_response(404)
        self.end_headers()


def main():
    global INI_PATH, CURRENT_PROFILE

    default_ini = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "SDVXTapeLedHook",
        "sdvxrgb.ini",
    )

    parser = argparse.ArgumentParser(description="SDVX RGB Web API")
    parser.add_argument(
        "--ini",
        default=default_ini,
        help="Path to sdvxrgb.ini (default: %(default)s)",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind to (default: %(default)s)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8274,
        help="Port to listen on (default: %(default)s)",
    )
    args = parser.parse_args()

    INI_PATH = os.path.abspath(args.ini)

    if not os.path.exists(INI_PATH):
        os.makedirs(os.path.dirname(INI_PATH), exist_ok=True)
        lines = []
        for name in STRIP_NAMES:
            lines.append(f"[{name}]")
            lines.append("")
        with open(INI_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  Created new INI file: {INI_PATH}")

    detect_current_profile()

    server = HTTPServer((args.host, args.port), Handler)
    print(f"SDVX RGB Web API")
    print(f"  INI path: {INI_PATH}")
    if CURRENT_PROFILE:
        print(f"  Active profile: {CURRENT_PROFILE}")
    print(f"  Listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
