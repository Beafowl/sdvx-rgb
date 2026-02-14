"""
SDVX RGB Controller

Real-time UI for adjusting LED color transformations per strip.
Reads shared memory for live preview, writes sdvxrgb.ini for the hook to hot-reload.

Usage:
    python sdvx_rgb_controller.py [path_to_sdvxrgb.ini]
"""

import colorsys
import mmap
import os
import sys
import tkinter as tk
from tkinter import colorchooser

DATA_SIZE = 1284
LED_COUNTS = [74, 12, 12, 56, 56, 94, 12, 12, 14, 86]
LED_OFFSETS = [0, 74, 86, 98, 154, 210, 304, 316, 328, 342]
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
STRIP_LABELS = [
    "Title",
    "Upper L Speaker",
    "Upper R Speaker",
    "Left Wing",
    "Right Wing",
    "Ctrl Panel",
    "Lower L Speaker",
    "Lower R Speaker",
    "Woofer",
    "V Unit",
]

# Modes
MODE_NONE = "none"
MODE_HUE = "hue"
MODE_STATIC = "static"
MODE_GRADIENT = "gradient"


class StripControl:
    """UI controls for a single LED strip."""

    def __init__(self, parent, strip_idx, on_change):
        self.strip_idx = strip_idx
        self.on_change = on_change

        self.frame = tk.LabelFrame(parent, text=STRIP_LABELS[strip_idx], padx=5, pady=5)
        self.frame.pack(fill=tk.X, padx=5, pady=2)

        top_row = tk.Frame(self.frame)
        top_row.pack(fill=tk.X)

        # Live preview canvas
        self.preview = tk.Canvas(top_row, width=30, height=30, bd=1, relief=tk.SUNKEN)
        self.preview.pack(side=tk.LEFT, padx=(0, 10))
        self.preview.create_rectangle(
            0, 0, 30, 30, fill="#000000", outline="", tags="bg"
        )

        # Mode radio buttons
        self.mode_var = tk.StringVar(value=MODE_NONE)
        tk.Radiobutton(
            top_row,
            text="No change",
            variable=self.mode_var,
            value=MODE_NONE,
            command=self._on_mode_change,
        ).pack(side=tk.LEFT)
        tk.Radiobutton(
            top_row,
            text="Hue shift",
            variable=self.mode_var,
            value=MODE_HUE,
            command=self._on_mode_change,
        ).pack(side=tk.LEFT)
        tk.Radiobutton(
            top_row,
            text="Static color",
            variable=self.mode_var,
            value=MODE_STATIC,
            command=self._on_mode_change,
        ).pack(side=tk.LEFT)
        tk.Radiobutton(
            top_row,
            text="Gradient",
            variable=self.mode_var,
            value=MODE_GRADIENT,
            command=self._on_mode_change,
        ).pack(side=tk.LEFT)

        # Hue shift controls
        self.hue_frame = tk.Frame(self.frame)
        tk.Label(self.hue_frame, text="Hue:").pack(side=tk.LEFT)
        self.hue_var = tk.IntVar(value=0)
        self.hue_slider = tk.Scale(
            self.hue_frame,
            from_=0,
            to=359,
            orient=tk.HORIZONTAL,
            variable=self.hue_var,
            command=self._on_slider_change,
            length=250,
        )
        self.hue_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Static color controls
        self.static_frame = tk.Frame(self.frame)
        self.color_hex = "#8000FF"
        self.color_btn = tk.Button(
            self.static_frame, text="Pick Color", command=self._pick_color
        )
        self.color_btn.pack(side=tk.LEFT)
        self.color_preview = tk.Canvas(
            self.static_frame, width=40, height=25, bd=1, relief=tk.SUNKEN
        )
        self.color_preview.pack(side=tk.LEFT, padx=5)
        self.color_preview.create_rectangle(
            0, 0, 40, 25, fill=self.color_hex, outline="", tags="cbg"
        )
        self.color_label = tk.Label(self.static_frame, text=self.color_hex)
        self.color_label.pack(side=tk.LEFT)

        # Gradient controls (two color pickers)
        self.gradient_frame = tk.Frame(self.frame)

        grad_row1 = tk.Frame(self.gradient_frame)
        grad_row1.pack(fill=tk.X)
        tk.Label(grad_row1, text="Color 1:").pack(side=tk.LEFT)
        self.grad_color1_hex = "#0000FF"
        self.grad_btn1 = tk.Button(grad_row1, text="Pick", command=self._pick_grad1)
        self.grad_btn1.pack(side=tk.LEFT, padx=3)
        self.grad_preview1 = tk.Canvas(
            grad_row1, width=40, height=20, bd=1, relief=tk.SUNKEN
        )
        self.grad_preview1.pack(side=tk.LEFT, padx=3)
        self.grad_preview1.create_rectangle(
            0, 0, 40, 20, fill=self.grad_color1_hex, outline="", tags="g1"
        )
        self.grad_label1 = tk.Label(grad_row1, text=self.grad_color1_hex)
        self.grad_label1.pack(side=tk.LEFT)

        grad_row2 = tk.Frame(self.gradient_frame)
        grad_row2.pack(fill=tk.X, pady=(3, 0))
        tk.Label(grad_row2, text="Color 2:").pack(side=tk.LEFT)
        self.grad_color2_hex = "#FF00FF"
        self.grad_btn2 = tk.Button(grad_row2, text="Pick", command=self._pick_grad2)
        self.grad_btn2.pack(side=tk.LEFT, padx=3)
        self.grad_preview2 = tk.Canvas(
            grad_row2, width=40, height=20, bd=1, relief=tk.SUNKEN
        )
        self.grad_preview2.pack(side=tk.LEFT, padx=3)
        self.grad_preview2.create_rectangle(
            0, 0, 40, 20, fill=self.grad_color2_hex, outline="", tags="g2"
        )
        self.grad_label2 = tk.Label(grad_row2, text=self.grad_color2_hex)
        self.grad_label2.pack(side=tk.LEFT)

        self._on_mode_change()

    def _on_mode_change(self):
        mode = self.mode_var.get()
        self.hue_frame.pack_forget()
        self.static_frame.pack_forget()
        self.gradient_frame.pack_forget()
        if mode == MODE_HUE:
            self.hue_frame.pack(fill=tk.X, pady=(3, 0))
        elif mode == MODE_STATIC:
            self.static_frame.pack(fill=tk.X, pady=(3, 0))
        elif mode == MODE_GRADIENT:
            self.gradient_frame.pack(fill=tk.X, pady=(3, 0))
        self.on_change()

    def _on_slider_change(self, _=None):
        self.on_change()

    def _pick_color(self):
        color = colorchooser.askcolor(
            color=self.color_hex, title=f"Pick color for {STRIP_LABELS[self.strip_idx]}"
        )
        if color[1]:
            self.color_hex = color[1]
            self.color_preview.itemconfig("cbg", fill=self.color_hex)
            self.color_label.config(text=self.color_hex)
            self.on_change()

    def _pick_grad1(self):
        color = colorchooser.askcolor(
            color=self.grad_color1_hex,
            title=f"Gradient color 1 for {STRIP_LABELS[self.strip_idx]}",
        )
        if color[1]:
            self.grad_color1_hex = color[1]
            self.grad_preview1.itemconfig("g1", fill=self.grad_color1_hex)
            self.grad_label1.config(text=self.grad_color1_hex)
            self.on_change()

    def _pick_grad2(self):
        color = colorchooser.askcolor(
            color=self.grad_color2_hex,
            title=f"Gradient color 2 for {STRIP_LABELS[self.strip_idx]}",
        )
        if color[1]:
            self.grad_color2_hex = color[1]
            self.grad_preview2.itemconfig("g2", fill=self.grad_color2_hex)
            self.grad_label2.config(text=self.grad_color2_hex)
            self.on_change()

    def get_ini_lines(self):
        """Return INI lines for this strip, or None if no change."""
        mode = self.mode_var.get()
        if mode == MODE_NONE:
            return None
        lines = [f"[{STRIP_NAMES[self.strip_idx]}]"]
        if mode == MODE_HUE:
            lines.append(f"hue_shift={self.hue_var.get()}")
        elif mode == MODE_STATIC:
            hex_color = self.color_hex.lstrip("#").upper()
            lines.append(f"static_color={hex_color}")
        elif mode == MODE_GRADIENT:
            hex1 = self.grad_color1_hex.lstrip("#").upper()
            hex2 = self.grad_color2_hex.lstrip("#").upper()
            lines.append(f"static_color={hex1}")
            lines.append(f"gradient_color={hex2}")
        return lines

    def update_preview(self, r, g, b):
        """Update the live preview with the average color from shared memory."""
        color = f"#{r:02x}{g:02x}{b:02x}"
        self.preview.itemconfig("bg", fill=color)


class SDVXController:
    def __init__(self, ini_path):
        self.ini_path = ini_path
        self.shm = None

        self.root = tk.Tk()
        self.root.title("SDVX RGB Controller")
        self.root.resizable(True, True)

        # INI path display
        path_frame = tk.Frame(self.root, padx=5, pady=5)
        path_frame.pack(fill=tk.X)
        tk.Label(path_frame, text="INI:").pack(side=tk.LEFT)
        tk.Label(path_frame, text=self.ini_path, fg="gray").pack(side=tk.LEFT, padx=5)

        # Status label
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(path_frame, textvariable=self.status_var, fg="green").pack(
            side=tk.RIGHT
        )

        # Scrollable frame for strip controls
        canvas = tk.Canvas(self.root)
        scrollbar = tk.Scrollbar(self.root, orient=tk.VERTICAL, command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas)

        self.scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scroll_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Create strip controls
        self.strips = []
        for i in range(10):
            ctrl = StripControl(self.scroll_frame, i, self._on_change)
            self.strips.append(ctrl)

        # Try opening shared memory
        try:
            self.shm = mmap.mmap(-1, DATA_SIZE, "sdvxrgb")
        except Exception:
            self.status_var.set("Shared memory not available (game not running?)")

        # Start preview update loop
        self._update_previews()

    def _on_change(self):
        """Write INI file when any control changes."""
        self._write_ini()

    def _write_ini(self):
        try:
            lines = []
            for strip in self.strips:
                strip_lines = strip.get_ini_lines()
                if strip_lines:
                    lines.extend(strip_lines)
                    lines.append("")

            with open(self.ini_path, "w") as f:
                f.write("\n".join(lines))

            self.status_var.set("Saved")
        except Exception as e:
            self.status_var.set(f"Error: {e}")

    def _update_previews(self):
        """Read shared memory and update strip color previews."""
        if self.shm:
            try:
                self.shm.seek(0)
                data = self.shm.read(DATA_SIZE)

                for i in range(10):
                    offset = LED_OFFSETS[i] * 3
                    count = LED_COUNTS[i]
                    total_r, total_g, total_b = 0, 0, 0
                    for led in range(count):
                        base = offset + led * 3
                        total_r += data[base]
                        total_g += data[base + 1]
                        total_b += data[base + 2]
                    avg_r = total_r // count
                    avg_g = total_g // count
                    avg_b = total_b // count
                    self.strips[i].update_preview(avg_r, avg_g, avg_b)
            except Exception:
                pass

        # Update every 100ms
        self.root.after(100, self._update_previews)

    def run(self):
        self.root.mainloop()


def main():
    if len(sys.argv) > 1:
        ini_path = sys.argv[1]
    else:
        ini_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "sdvxrgb.ini"
        )

    app = SDVXController(ini_path)
    app.run()


if __name__ == "__main__":
    main()
