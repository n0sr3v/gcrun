import argparse
import re
from pathlib import Path


AXIS_WORD = re.compile(r"\b([XYZEF])\s*(-?\d+(?:\.\d+)?)", re.I)
G_WORD = re.compile(r"\bG(\d+)(?:\.\d+)?\b", re.I)
M_WORD = re.compile(r"\bM(\d+)(?:\.\d+)?\b", re.I)


def strip_comments(line):
    line = re.sub(r"\([^)]*\)", "", line)
    return line.split(";", 1)[0].strip()


def normalize_line(line, motion_mode):
    line = strip_comments(line)
    if not line:
        return [], motion_mode

    upper = line.upper()
    g_codes = [int(code) for code in G_WORD.findall(upper)]
    m_codes = [int(code) for code in M_WORD.findall(upper)]

    if any(code in {17, 18, 19} for code in g_codes):
        g_codes = [code for code in g_codes if code not in {17, 18, 19}]
        words = []
        for word in upper.split():
            if word in {"G17", "G18", "G19"}:
                continue
            words.append(word)
        upper = " ".join(words)
        line = upper

    if any(code in {2, 3} for code in g_codes):
        raise ValueError(f"Arc command remains after linearization: {line}")

    if len([code for code in g_codes if code in {0, 1}]) > 1:
        raise ValueError(f"Multiple motion commands on one line: {line}")

    output = []
    motion_codes = [code for code in g_codes if code in {0, 1}]
    if motion_codes:
        motion_mode = f"G{motion_codes[-1]}"
        output.append(line)
        return output, motion_mode

    if g_codes:
        allowed = {21, 90}
        unknown = [code for code in g_codes if code not in allowed]
        if unknown:
            raise ValueError(f"Unsupported G-code after normalization: {line}")
        output.append(line)
        return output, motion_mode

    if m_codes:
        output.append(line)
        return output, motion_mode

    if AXIS_WORD.search(line):
        if not motion_mode:
            raise ValueError(f"Axis-only line before motion mode is known: {line}")
        output.append(f"{motion_mode} {line}")
        return output, motion_mode

    return output, motion_mode


def normalize_file(src, dst, max_lines=None):
    motion_mode = None
    emitted = 0
    out = [
        "; Normalized for this Marlin build: explicit G0/G1, no G17/G18/G19, no arcs.",
        "; Source: " + str(src),
    ]
    for raw in src.read_text(encoding="utf-8", errors="ignore").splitlines():
        lines, motion_mode = normalize_line(raw, motion_mode)
        for line in lines:
            out.append(line)
            emitted += 1
            if max_lines and emitted >= max_lines:
                out.append("M400")
                dst.write_text("\n".join(out) + "\n")
                return
    dst.write_text("\n".join(out) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src", type=Path)
    parser.add_argument("dst", type=Path)
    parser.add_argument("--max-lines", type=int)
    args = parser.parse_args()
    normalize_file(args.src, args.dst, args.max_lines)


if __name__ == "__main__":
    main()
