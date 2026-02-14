"""
SDVX RGB Capture Tool

Captures LED data from shared memory for comparison between game versions.

Usage:
    python sdvx_rgb_capture.py record <output_file>     - Record LED data to a .sdvxcap file
    python sdvx_rgb_capture.py dump <capture_file>       - Print per-strip statistics
    python sdvx_rgb_capture.py compare <old> <new>       - Compare two capture files
"""

import argparse
import colorsys
import mmap
import struct
import sys
import time

DATA_SIZE = 1284
LED_COUNTS = [74, 12, 12, 56, 56, 94, 12, 12, 14, 86]
LED_OFFSETS = [0, 74, 86, 98, 154, 210, 304, 316, 328, 342]
LED_NAMES = [
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

# Frame format: 8-byte double timestamp + 1284 bytes RGB data
FRAME_SIZE = 8 + DATA_SIZE


def record(output_path):
    """Record LED data from shared memory to a binary file."""
    try:
        shm = mmap.mmap(-1, DATA_SIZE, "sdvxrgb")
    except Exception as e:
        print(f"Failed to open shared memory 'sdvxrgb': {e}")
        print("Make sure the game is running with the hook loaded.")
        sys.exit(1)

    last_data = None
    frame_count = 0

    print(f"Recording to {output_path} ... Press Ctrl+C to stop.")

    try:
        with open(output_path, "wb") as f:
            while True:
                shm.seek(0)
                data = shm.read(DATA_SIZE)

                # Skip duplicate frames
                if data == last_data:
                    time.sleep(1.0 / 60.0)
                    continue

                last_data = data
                timestamp = time.time()
                f.write(struct.pack("d", timestamp))
                f.write(data)
                f.flush()
                frame_count += 1

                if frame_count % 60 == 0:
                    print(f"  {frame_count} frames captured", end="\r")

                time.sleep(1.0 / 60.0)

    except KeyboardInterrupt:
        print(f"\nStopped. {frame_count} frames saved to {output_path}")


def read_capture(path):
    """Read all frames from a .sdvxcap file. Returns list of (timestamp, data) tuples."""
    frames = []
    with open(path, "rb") as f:
        while True:
            header = f.read(8)
            if len(header) < 8:
                break
            timestamp = struct.unpack("d", header)[0]
            data = f.read(DATA_SIZE)
            if len(data) < DATA_SIZE:
                break
            frames.append((timestamp, data))
    return frames


def compute_strip_stats(frames):
    """Compute per-strip average brightness, hue distribution, and saturation."""
    stats = []
    for strip_idx in range(10):
        offset = LED_OFFSETS[strip_idx] * 3
        count = LED_COUNTS[strip_idx]

        total_r, total_g, total_b = 0.0, 0.0, 0.0
        total_brightness = 0.0
        total_saturation = 0.0
        hue_counts = [0] * 36  # 10-degree buckets
        num_pixels = 0

        for _, data in frames:
            for led in range(count):
                base = offset + led * 3
                r = data[base]
                g = data[base + 1]
                b = data[base + 2]

                total_r += r
                total_g += g
                total_b += b
                total_brightness += max(r, g, b)

                # HSV analysis (skip black pixels)
                if r > 0 or g > 0 or b > 0:
                    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                    total_saturation += s
                    bucket = int(h * 36) % 36
                    hue_counts[bucket] += 1

                num_pixels += 1

        if num_pixels > 0:
            avg_r = total_r / num_pixels
            avg_g = total_g / num_pixels
            avg_b = total_b / num_pixels
            avg_brightness = total_brightness / num_pixels
            avg_saturation = total_saturation / num_pixels if num_pixels > 0 else 0
        else:
            avg_r = avg_g = avg_b = avg_brightness = avg_saturation = 0

        # Find dominant hue bucket
        max_hue_bucket = (
            max(range(36), key=lambda i: hue_counts[i]) if any(hue_counts) else 0
        )
        dominant_hue_deg = max_hue_bucket * 10

        stats.append(
            {
                "name": LED_NAMES[strip_idx],
                "count": LED_COUNTS[strip_idx],
                "avg_r": avg_r,
                "avg_g": avg_g,
                "avg_b": avg_b,
                "avg_brightness": avg_brightness,
                "avg_saturation": avg_saturation,
                "dominant_hue": dominant_hue_deg,
                "hue_distribution": hue_counts,
            }
        )

    return stats


def dump(capture_path):
    """Print per-strip statistics from a capture file."""
    frames = read_capture(capture_path)
    if not frames:
        print("No frames found in capture file.")
        return

    duration = frames[-1][0] - frames[0][0] if len(frames) > 1 else 0
    print(f"Capture: {capture_path}")
    print(f"  Frames: {len(frames)}")
    print(f"  Duration: {duration:.1f}s")
    print()

    stats = compute_strip_stats(frames)

    print(
        f"{'Strip':<24} {'LEDs':>5} {'Avg R':>6} {'Avg G':>6} {'Avg B':>6} {'Bright':>7} {'Sat':>5} {'Hue':>5}"
    )
    print("-" * 80)
    for s in stats:
        print(
            f"{s['name']:<24} {s['count']:>5} {s['avg_r']:>6.1f} {s['avg_g']:>6.1f} {s['avg_b']:>6.1f} "
            f"{s['avg_brightness']:>7.1f} {s['avg_saturation']:>5.2f} {s['dominant_hue']:>4}d"
        )


def compare(old_path, new_path):
    """Compare two capture files and report differences."""
    old_frames = read_capture(old_path)
    new_frames = read_capture(new_path)

    if not old_frames:
        print(f"No frames in {old_path}")
        return
    if not new_frames:
        print(f"No frames in {new_path}")
        return

    print(f"Old: {old_path} ({len(old_frames)} frames)")
    print(f"New: {new_path} ({len(new_frames)} frames)")
    print()

    old_stats = compute_strip_stats(old_frames)
    new_stats = compute_strip_stats(new_frames)

    print(
        f"{'Strip':<24} {'dR':>6} {'dG':>6} {'dB':>6} {'dBright':>8} {'dSat':>6} {'Old Hue':>8} {'New Hue':>8}"
    )
    print("-" * 90)

    for o, n in zip(old_stats, new_stats):
        dr = n["avg_r"] - o["avg_r"]
        dg = n["avg_g"] - o["avg_g"]
        db = n["avg_b"] - o["avg_b"]
        dbright = n["avg_brightness"] - o["avg_brightness"]
        dsat = n["avg_saturation"] - o["avg_saturation"]

        print(
            f"{o['name']:<24} {dr:>+6.1f} {dg:>+6.1f} {db:>+6.1f} "
            f"{dbright:>+8.1f} {dsat:>+6.2f} {o['dominant_hue']:>7}d {n['dominant_hue']:>7}d"
        )

    print()
    print("Suggested INI adjustments:")
    print("-" * 40)

    for o, n in zip(old_stats, new_stats):
        dbright = n["avg_brightness"] - o["avg_brightness"]
        dsat = n["avg_saturation"] - o["avg_saturation"]

        suggestions = []

        # Brightness: if new is brighter, suggest reducing; if dimmer, suggest increasing
        if abs(dbright) > 5:
            if o["avg_brightness"] > 0:
                ratio = (
                    o["avg_brightness"] / n["avg_brightness"]
                    if n["avg_brightness"] > 0
                    else 1.0
                )
                suggested_brightness = int(ratio * 100)
                suggested_brightness = max(0, min(200, suggested_brightness))
                suggestions.append(f"brightness={suggested_brightness}")

        # Saturation
        if abs(dsat) > 0.05:
            if n["avg_saturation"] > 0:
                ratio = o["avg_saturation"] / n["avg_saturation"]
                suggested_sat = int(ratio * 100)
                suggested_sat = max(0, min(200, suggested_sat))
                suggestions.append(f"saturation={suggested_sat}")

        # Hue shift
        if o["dominant_hue"] != n["dominant_hue"]:
            shift = (o["dominant_hue"] - n["dominant_hue"]) % 360
            if shift != 0:
                suggestions.append(f"hue_shift={shift}")

        if suggestions:
            print(f"[{o['name']}]")
            for s in suggestions:
                print(f"  {s}")
            print()


def main():
    parser = argparse.ArgumentParser(
        description="SDVX RGB Capture Tool - record, dump, and compare LED data"
    )
    subparsers = parser.add_subparsers(dest="command")

    record_parser = subparsers.add_parser(
        "record", help="Record LED data from shared memory"
    )
    record_parser.add_argument("output", help="Output .sdvxcap file path")

    dump_parser = subparsers.add_parser(
        "dump", help="Print statistics from a capture file"
    )
    dump_parser.add_argument("capture", help="Input .sdvxcap file path")

    compare_parser = subparsers.add_parser("compare", help="Compare two capture files")
    compare_parser.add_argument("old", help="Old version capture file")
    compare_parser.add_argument("new", help="New version capture file")

    args = parser.parse_args()

    if args.command == "record":
        record(args.output)
    elif args.command == "dump":
        dump(args.capture)
    elif args.command == "compare":
        compare(args.old, args.new)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
