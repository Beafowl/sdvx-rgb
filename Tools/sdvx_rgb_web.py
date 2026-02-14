"""
SDVX RGB Web API

Minimal web API + frontend for editing sdvxrgb.ini.
Uses only the Python standard library (no Flask/etc).

Usage:
    python sdvx_rgb_web.py [path_to_sdvxrgb.ini] [--host HOST] [--port PORT]

Then open http://localhost:8274 in a browser.
"""

import argparse
import configparser
import json
import os
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

        self.send_response(404)
        self.end_headers()


def main():
    global INI_PATH

    default_ini = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "SDVXTapeLedHook",
        "sdvxrgb.ini",
    )

    parser = argparse.ArgumentParser(description="SDVX RGB Web API")
    parser.add_argument(
        "ini",
        nargs="?",
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

    server = HTTPServer((args.host, args.port), Handler)
    print(f"SDVX RGB Web API")
    print(f"  INI path: {INI_PATH}")
    print(f"  Listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
