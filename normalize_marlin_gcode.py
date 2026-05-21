import argparse
import math
import re
from pathlib import Path


WORD_RE = re.compile(r"([A-Z])\s*(-?\d+(?:\.\d+)?)", re.I)
COMMENT_RE = re.compile(r"\([^)]*\)")
AXES = ("X", "Y", "Z")
PLANE_OFFSETS = {
    "G17": ("X", "Y", "I", "J"),
    "G18": ("X", "Z", "I", "K"),
    "G19": ("Y", "Z", "J", "K"),
}


class ConverterError(ValueError):
    pass


def strip_comments(line):
    line = COMMENT_RE.sub("", line)
    return line.split(";", 1)[0].strip()


def parse_words(line):
    return [(letter.upper(), float(value)) for letter, value in WORD_RE.findall(line)]


def format_number(value):
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text != "-0" else "0"


def format_linear(mode, pos, feed=None, axes=None):
    axes = axes or AXES
    parts = [mode]
    for axis in axes:
        parts.append(f"{axis}{format_number(pos[axis])}")
    if feed is not None:
        parts.append(f"F{format_number(feed)}")
    return " ".join(parts)


def arc_points(start, target, center, plane, clockwise, tolerance):
    axis_u, axis_v, _, _ = PLANE_OFFSETS[plane]
    radius_u = start[axis_u] - center[axis_u]
    radius_v = start[axis_v] - center[axis_v]
    end_radius_u = target[axis_u] - center[axis_u]
    end_radius_v = target[axis_v] - center[axis_v]
    radius = math.hypot(radius_u, radius_v)
    if radius <= 0:
        raise ConverterError("Arc radius is zero")

    start_angle = math.atan2(radius_v, radius_u)
    end_angle = math.atan2(end_radius_v, end_radius_u)
    delta = end_angle - start_angle
    if clockwise:
        if delta >= 0:
            delta -= math.tau
    else:
        if delta <= 0:
            delta += math.tau
    if abs(delta) < 1e-9:
        delta = -math.tau if clockwise else math.tau

    chord = max(tolerance, 0.01)
    max_angle = 2 * math.acos(max(-1.0, min(1.0, 1 - chord / radius)))
    if not math.isfinite(max_angle) or max_angle <= 0:
        max_angle = math.radians(5)
    segments = max(1, int(math.ceil(abs(delta) / min(max_angle, math.radians(10)))))

    points = []
    for index in range(1, segments + 1):
        fraction = index / segments
        angle = start_angle + delta * fraction
        point = dict(start)
        point[axis_u] = center[axis_u] + math.cos(angle) * radius
        point[axis_v] = center[axis_v] + math.sin(angle) * radius
        for axis in AXES:
            if axis not in (axis_u, axis_v):
                point[axis] = start[axis] + (target[axis] - start[axis]) * fraction
        points.append(point)
    points[-1].update(target)
    return points


def convert_lines(raw_lines, tolerance=0.05, initial_z=16.5, include_comments=True):
    pos = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    plane = "G17"
    motion_mode = None
    absolute = True
    emitted_setup = False
    output = [
        "; Marlin-safe conversion from Fusion 360 GRBL-style G-code.",
        "; Emits explicit G0/G1 only; arcs and plane changes are linearized/removed.",
        "; Set work origin in the controller/UI before running this file.",
        "G21",
        "G90",
        "M17",
        f"G0 Z{format_number(initial_z)}",
    ]

    def ensure_absolute():
        if not absolute:
            raise ConverterError("Relative coordinate mode (G91) is not supported in cutting moves")

    for raw_number, raw in enumerate(raw_lines, start=1):
        clean = strip_comments(raw)
        if not clean:
            continue
        words = parse_words(clean)
        if not words:
            continue

        letters = {}
        for letter, value in words:
            letters.setdefault(letter, []).append(value)

        g_codes = [int(value) for letter, value in words if letter == "G"]
        m_codes = [int(value) for letter, value in words if letter == "M"]

        if any(code == 91 for code in g_codes):
            absolute = False
        if any(code == 90 for code in g_codes):
            absolute = True
        if any(code == 21 for code in g_codes):
            emitted_setup = True
        if any(code == 17 for code in g_codes):
            plane = "G17"
        if any(code == 18 for code in g_codes):
            plane = "G18"
        if any(code == 19 for code in g_codes):
            plane = "G19"

        if any(code == 28 for code in g_codes):
            continue
        if any(54 <= code <= 59 for code in g_codes):
            continue
        if any(code in {94, 17, 18, 19, 21, 90, 91} for code in g_codes) and not any(
            code in {0, 1, 2, 3} for code in g_codes
        ):
            continue
        if any(code in {3, 4, 5, 30} for code in m_codes):
            continue
        if "T" in letters or ("S" in letters and not any(code in {0, 1, 2, 3} for code in g_codes)):
            continue

        feed = letters.get("F", [None])[-1]
        axis_values = {axis: letters[axis][-1] for axis in AXES if axis in letters}
        target = dict(pos)
        for axis, value in axis_values.items():
            target[axis] = value if absolute else pos[axis] + value

        motion_codes = [code for code in g_codes if code in {0, 1, 2, 3}]
        if motion_codes:
            motion_mode = f"G{motion_codes[-1]}"

        if not motion_codes and axis_values and motion_mode:
            motion = motion_mode
        elif motion_codes:
            motion = motion_mode
        else:
            motion = None

        if motion in {"G0", "G1"}:
            ensure_absolute()
            if not axis_values and feed is None:
                continue
            pos = target
            changed_axes = [axis for axis in AXES if axis in axis_values]
            output.append(format_linear(motion, pos, feed=feed, axes=changed_axes))
            continue

        if motion in {"G2", "G3"}:
            ensure_absolute()
            axis_u, axis_v, offset_u, offset_v = PLANE_OFFSETS[plane]
            if offset_u not in letters or offset_v not in letters:
                raise ConverterError(f"Line {raw_number}: arcs must use center offsets: {clean}")
            center = dict(pos)
            center[axis_u] = pos[axis_u] + letters[offset_u][-1]
            center[axis_v] = pos[axis_v] + letters[offset_v][-1]
            points = arc_points(pos, target, center, plane, clockwise=motion == "G2", tolerance=tolerance)
            for index, point in enumerate(points):
                output.append(format_linear("G1", point, feed=feed if index == 0 else None))
            pos = target
            motion_mode = "G1"
            continue

        if m_codes:
            for code in m_codes:
                if code in {17, 400}:
                    output.append(f"M{code}")
            continue

        ignored = " ".join(f"{letter}{format_number(value)}" for letter, value in words)
        if include_comments:
            output.append(f"; skipped unsupported/non-motion line {raw_number}: {ignored}")

    if not emitted_setup:
        output.insert(3, "; Source did not explicitly request metric mode; assuming millimeters.")
    output.extend(["M400", "G90", "G0 Z16.5", "G0 X0 Y0", "M400"])
    return output


def normalize_file(src, dst, tolerance=0.05, initial_z=16.5, max_lines=None):
    raw_lines = src.read_text(encoding="utf-8", errors="ignore").splitlines()
    converted = convert_lines(raw_lines, tolerance=tolerance, initial_z=initial_z)
    if max_lines is not None:
        header = converted[:6]
        body = converted[6:-5][:max_lines]
        converted = header + body + ["M400"]
    dst.write_text("\n".join(converted) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Convert Fusion 360 GRBL-style G-code to Marlin-safe G0/G1.")
    parser.add_argument("src", type=Path)
    parser.add_argument("dst", type=Path)
    parser.add_argument("--tolerance", type=float, default=0.05, help="Arc linearization chord tolerance in mm.")
    parser.add_argument("--initial-z", type=float, default=16.5, help="Safe Z-hop inserted before first XY travel.")
    parser.add_argument("--max-lines", type=int, help="Emit only this many converted motion/body lines.")
    args = parser.parse_args()
    normalize_file(args.src, args.dst, tolerance=args.tolerance, initial_z=args.initial_z, max_lines=args.max_lines)


if __name__ == "__main__":
    main()
