import argparse
import re
import socket
import sys
import time
from pathlib import Path

import serial


DEFAULT_PORT = "socket://127.0.0.1:2323"
DEFAULT_BAUD = 250000
CONTROL_PREFIX = re.compile(r"^[\x00-\x08\x0b\x0c\x0e-\x1f]+")
AXIS_RE = re.compile(r"\b([XYZ])\s*(-?\d+(?:\.\d+)?)", re.I)
UNSUPPORTED_RE = re.compile(r"\bG(17|18|19|2|3)\b", re.I)
BARE_MODAL_RE = re.compile(r"^[XYZEFIJK]", re.I)


def clean_response(raw):
    return CONTROL_PREFIX.sub("", raw.decode(errors="ignore").strip()).strip()


def clean_line(raw):
    return raw.split(";", 1)[0].strip()


def load_commands(path):
    commands = []
    for raw in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = clean_line(raw)
        if line:
            commands.append(line)
    return commands


def validate_commands(commands, allow_negative_xy=False):
    ranges = {axis: [float("inf"), float("-inf")] for axis in "XYZ"}
    for index, line in enumerate(commands, 1):
        if UNSUPPORTED_RE.search(line):
            raise ValueError(f"Unsupported arc/plane command at command {index}: {line}")
        if BARE_MODAL_RE.match(line):
            raise ValueError(f"Bare modal axis/feed line at command {index}: {line}")
        for axis, value in AXIS_RE.findall(line):
            numeric = float(value)
            if axis.upper() in {"X", "Y"} and numeric < 0 and not allow_negative_xy:
                raise ValueError(f"Negative {axis.upper()} at command {index}: {line}")
            ranges[axis.upper()][0] = min(ranges[axis.upper()][0], numeric)
            ranges[axis.upper()][1] = max(ranges[axis.upper()][1], numeric)
    return {axis: tuple(value) for axis, value in ranges.items() if value[0] != float("inf")}


def open_serial(port, baud):
    return serial.serial_for_url(port, baudrate=baud, timeout=0.5)


def read_until_ok(ser, sent, timeout=300, echo=False):
    deadline = time.time() + timeout
    while True:
        raw = ser.readline()
        if raw:
            message = clean_response(raw)
            low = message.lower()
            if echo and message:
                print(f"<< {message}", flush=True)
            if low == "ok" or low.startswith("ok "):
                return
            if low.startswith("error") or low.startswith("echo:error"):
                raise RuntimeError(f"Marlin error after {sent}: {message}")
            if "unknown command" in low:
                raise RuntimeError(f"Marlin rejected {sent}: {message}")
            if low.startswith("echo:busy"):
                deadline = time.time() + timeout
        if time.time() > deadline:
            raise TimeoutError(f"Timed out waiting for ok after: {sent}")


def send_command(ser, line, timeout=300, verbose=False):
    if verbose:
        print(f">> {line}", flush=True)
    ser.write((line + "\n").encode())
    ser.flush()
    read_until_ok(ser, line, timeout=timeout, echo=verbose)


def query_position(port, baud):
    with open_serial(port, baud) as ser:
        ser.write(b"M114\n")
        ser.flush()
        deadline = time.time() + 10
        while time.time() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            message = clean_response(raw)
            if message:
                print(message)
            if message.lower().startswith("ok"):
                return
    raise TimeoutError("No complete M114 response")


def quickstop(port, baud):
    with open_serial(port, baud) as ser:
        for command in ("M410", "M400", "M114"):
            print(f">> {command}", flush=True)
            ser.write((command + "\n").encode())
            ser.flush()
            read_until_ok(ser, command, timeout=120, echo=True)


def lift_z(port, baud, amount):
    with open_serial(port, baud) as ser:
        for command in ("G91", f"G0 Z{amount:g} F600", "G90", "M400", "M114"):
            print(f">> {command}", flush=True)
            send_command(ser, command, timeout=180, verbose=True)


def run_file(args):
    commands = load_commands(args.file)
    ranges = validate_commands(commands, allow_negative_xy=args.allow_negative_xy)
    print(f"file: {args.file}")
    print(f"commands: {len(commands)}")
    print(f"ranges: {ranges}")
    if args.dry_check:
        return
    if not args.yes:
        raise SystemExit("Refusing to run without --yes")

    start = time.time()
    with open_serial(args.port, args.baud) as ser:
        if args.surface_z is not None:
            preflight = ["G21", "G90", f"G92 X0 Y0 Z{args.surface_z:g}", "M114"]
            for command in preflight:
                print(f"PRE >> {command}", flush=True)
                send_command(ser, command, timeout=60, verbose=args.verbose)
        for index, command in enumerate(commands, 1):
            send_command(ser, command, timeout=args.timeout, verbose=args.verbose)
            if index == 1 or index % args.progress == 0 or index == len(commands):
                print(
                    f"PROGRESS {index}/{len(commands)} elapsed={time.time() - start:.1f}s last={command}",
                    flush=True,
                )
        print("POST >> M400", flush=True)
        send_command(ser, "M400", timeout=600, verbose=args.verbose)
        print("POST >> M114", flush=True)
        ser.write(b"M114\n")
        ser.flush()
        deadline = time.time() + 30
        while time.time() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            message = clean_response(raw)
            if message:
                print(f"<< {message}", flush=True)
            if message.lower().startswith("ok"):
                break
    print(f"COMPLETE elapsed={time.time() - start:.1f}s")


def probe_port(port):
    host, port_text = port.rsplit(":", 1)
    if host.endswith("//127.0.0.1"):
        host = "127.0.0.1"
    with socket.create_connection((host, int(port_text)), timeout=2):
        print(f"{host}:{port_text} open")


def main():
    parser = argparse.ArgumentParser(description="CNC/Marlin bridge runner for the Termux setup.")
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("pos")
    sub.add_parser("stop")

    lift = sub.add_parser("lift")
    lift.add_argument("amount", type=float, help="Relative Z lift in mm.")

    probe = sub.add_parser("probe")

    run = sub.add_parser("run")
    run.add_argument("file", type=Path)
    run.add_argument("--surface-z", type=float, help="Set current touch point with G92 X0 Y0 Z<value> before running.")
    run.add_argument("--timeout", type=float, default=300)
    run.add_argument("--progress", type=int, default=50)
    run.add_argument("--verbose", action="store_true")
    run.add_argument("--dry-check", action="store_true")
    run.add_argument("--yes", action="store_true")
    run.add_argument(
        "--allow-negative-xy",
        action="store_true",
        help="Allow jobs whose work origin is not bottom-left, such as top-center with negative Y.",
    )

    args = parser.parse_args()
    if args.command == "pos":
        query_position(args.port, args.baud)
    elif args.command == "stop":
        quickstop(args.port, args.baud)
    elif args.command == "lift":
        lift_z(args.port, args.baud, args.amount)
    elif args.command == "probe":
        probe_port(args.port)
    elif args.command == "run":
        run_file(args)
    else:
        raise AssertionError(args.command)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted. Sender stopped; Marlin may still be draining queued motion.", file=sys.stderr)
        raise
