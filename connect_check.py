import argparse
import json
import os
import socket
import subprocess
import sys
import time


DEFAULT_PORTS = [2323, 8080, 8888, 9000]


def run(cmd, timeout=3):
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc), "stdout": "", "stderr": ""}
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def print_section(title):
    print(f"\n== {title} ==")


def check_termux_usb():
    print_section("Termux USB")
    if not os.path.exists("/data/data/com.termux/files/usr/bin/termux-usb"):
        print("termux-usb: not installed")
        return
    result = run(["termux-usb", "-l"], timeout=3)
    if result["ok"]:
        try:
            devices = json.loads(result["stdout"])
        except json.JSONDecodeError:
            devices = result["stdout"]
        print(f"termux-usb -l: {devices}")
    else:
        detail = result["stderr"] or result["stdout"] or result["error"]
        print(f"termux-usb -l failed: {detail}")


def check_serial_nodes():
    print_section("Linux Serial Nodes")
    found = []
    for prefix in ("ttyUSB", "ttyACM"):
        for index in range(8):
            path = f"/dev/{prefix}{index}"
            if os.path.exists(path):
                found.append(path)
    if found:
        print("\n".join(sorted(found)))
    else:
        print("No /dev/ttyUSB* or /dev/ttyACM* nodes visible to Termux")


def check_installed_apps():
    print_section("Relevant Android Packages")
    result = run(["pm", "list", "packages"], timeout=3)
    if not result["ok"]:
        print(result["stderr"] or result["stdout"] or result["error"])
        return
    matches = [
        line
        for line in result["stdout"].splitlines()
        if any(token in line.lower() for token in ("termux", "serial", "usb", "console", "bridge"))
    ]
    print("\n".join(matches) if matches else "No obvious USB serial bridge package found")


def socket_probe(port, command=None, timeout=2):
    host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect((host, port))
        if command:
            sock.sendall((command.strip() + "\n").encode())
            time.sleep(0.5)
            try:
                return sock.recv(4096).decode(errors="ignore").strip()
            except socket.timeout:
                return ""
        return ""


def check_tcp_ports(ports, command=None):
    print_section("Local TCP Bridges")
    for port in ports:
        try:
            reply = socket_probe(port, command=command)
        except Exception as exc:
            print(f"127.0.0.1:{port} closed: {exc}")
            continue
        print(f"127.0.0.1:{port} open")
        if command:
            print(f"reply: {reply or '<no immediate reply>'}")


def main():
    parser = argparse.ArgumentParser(description="Check Android/Termux CNC connection paths.")
    parser.add_argument(
        "--ports",
        default=",".join(str(port) for port in DEFAULT_PORTS),
        help="Comma-separated TCP bridge ports to test.",
    )
    parser.add_argument(
        "--command",
        default="",
        help="Optional G-code command to send to an open TCP bridge, e.g. M115.",
    )
    args = parser.parse_args()
    ports = [int(item.strip()) for item in args.ports.split(",") if item.strip()]

    print(f"python: {sys.version.split()[0]}")
    print(f"platform: {sys.platform}")
    check_serial_nodes()
    check_termux_usb()
    check_installed_apps()
    check_tcp_ports(ports, command=args.command.strip() or None)


if __name__ == "__main__":
    main()
