import ctypes
import argparse
import select
import sys
import time


LIBUSB = "/data/data/com.termux/files/usr/lib/libusb-1.0.so"
FTDI_IN = 0x81
FTDI_OUT = 0x02
BAUDRATE_REF_BASE = 3000000
FRAC_DIV_CODE = (0, 3, 2, 4, 1, 5, 6, 7)


def log(message):
    print(message, flush=True)


def configure_libusb(lib):
    lib.libusb_init.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    lib.libusb_init.restype = ctypes.c_int
    lib.libusb_set_option.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_set_option.restype = ctypes.c_int
    lib.libusb_wrap_sys_device.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ssize_t,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    lib.libusb_wrap_sys_device.restype = ctypes.c_int
    lib.libusb_control_transfer.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint8,
        ctypes.c_uint8,
        ctypes.c_uint16,
        ctypes.c_uint16,
        ctypes.c_void_p,
        ctypes.c_uint16,
        ctypes.c_uint,
    ]
    lib.libusb_control_transfer.restype = ctypes.c_int
    lib.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_claim_interface.restype = ctypes.c_int
    lib.libusb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_release_interface.restype = ctypes.c_int
    lib.libusb_bulk_transfer.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ubyte,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_uint,
    ]
    lib.libusb_bulk_transfer.restype = ctypes.c_int
    lib.libusb_close.argtypes = [ctypes.c_void_p]
    lib.libusb_close.restype = None
    lib.libusb_exit.argtypes = [ctypes.c_void_p]
    lib.libusb_exit.restype = None
    if hasattr(lib, "libusb_set_auto_detach_kernel_driver"):
        lib.libusb_set_auto_detach_kernel_driver.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.libusb_set_auto_detach_kernel_driver.restype = ctypes.c_int


def convert_baudrate(baudrate):
    if baudrate > BAUDRATE_REF_BASE:
        raise ValueError(f"baudrate too high for FTDI full-speed mode: {baudrate}")
    if baudrate < ((BAUDRATE_REF_BASE >> 14) + 1):
        raise ValueError(f"baudrate too low: {baudrate}")
    div8 = int(round((8 * BAUDRATE_REF_BASE) / baudrate))
    div = div8 >> 3
    div |= FRAC_DIV_CODE[div8 & 0x7] << 14
    if div == 1:
        div = 0
    elif div == 0x4001:
        div = 1
    value = div & 0xFFFF
    index = (div >> 16) & 0xFFFF
    actual = int(((8 * BAUDRATE_REF_BASE) + (div8 // 2)) // div8)
    return actual, value, index


def ctrl(lib, handle, request, value, index=0, label="control"):
    res = lib.libusb_control_transfer(handle, 0x40, request, value, index, None, 0, 1000)
    log(f"{label}: {res}")
    return res


def configure_serial(lib, handle, baudrate):
    actual, value, index = convert_baudrate(baudrate)
    log(f"configuring baud requested={baudrate} actual={actual} value=0x{value:04x} index=0x{index:04x}")
    for request, ctrl_value, ctrl_index, label in (
        (0, 1, 0, "purge rx"),
        (0, 2, 0, "purge tx"),
        (3, value, index, f"baud {baudrate}"),
        (4, 8, 0, "8N1"),
        (2, 0, 0, "flow none"),
    ):
        res = ctrl(lib, handle, request, ctrl_value, ctrl_index, label=label)
        if res < 0:
            return False
    return True


def bulk_write(lib, handle, data):
    buf = ctypes.create_string_buffer(data)
    transferred = ctypes.c_int()
    res = lib.libusb_bulk_transfer(handle, FTDI_OUT, buf, len(data), ctypes.byref(transferred), 1000)
    log(f"write {data!r}: res={res} transferred={transferred.value}")
    return res, transferred.value


def strip_ftdi_status(raw):
    payload = bytearray()
    for offset in range(0, len(raw), 64):
        packet = raw[offset : offset + 64]
        if len(packet) > 2:
            payload.extend(packet[2:])
    return bytes(payload)


def bulk_read(lib, handle, seconds):
    deadline = time.time() + seconds
    payload = bytearray()
    while time.time() < deadline:
        buf = ctypes.create_string_buffer(512)
        transferred = ctypes.c_int()
        res = lib.libusb_bulk_transfer(handle, FTDI_IN, buf, 512, ctypes.byref(transferred), 100)
        if res == 0 and transferred.value > 2:
            payload.extend(strip_ftdi_status(buf.raw[: transferred.value]))
        elif res not in (0, -7):
            log(f"read res={res} transferred={transferred.value}")
        time.sleep(0.02)
    if payload:
        print(payload.decode(errors="replace"), end="", flush=True)
    log(f"\nread bytes: {len(payload)}")
    return bytes(payload)


def probe_baud(lib, handle, baudrate, dtr=False):
    log(f"\n== probing {baudrate} baud ==")
    if not configure_serial(lib, handle, baudrate):
        return b""
    if dtr:
        ctrl(lib, handle, 1, 0x0101, label="DTR on")
        ctrl(lib, handle, 1, 0x0202, label="RTS on")
        bulk_read(lib, handle, 2)
    bulk_write(lib, handle, b"\n")
    time.sleep(0.2)
    bulk_write(lib, handle, b"M115\n")
    reply = bulk_read(lib, handle, 4)
    if b"FIRMWARE_NAME" in reply or b"ok" in reply.lower():
        log(f"matched response at {baudrate} baud")
    return reply


def main():
    parser = argparse.ArgumentParser(
        description="Probe an FTDI Marlin/GRBL USB serial adapter from a termux-usb FD."
    )
    parser.add_argument("fd", type=int, help="USB file descriptor passed by termux-usb")
    parser.add_argument("--baud", type=int, default=250000, help="Single baud rate to test.")
    parser.add_argument(
        "--sweep",
        default="",
        help="Comma-separated baud rates to test instead of --baud, e.g. 115200,250000.",
    )
    parser.add_argument(
        "--dtr",
        action="store_true",
        help="Assert DTR/RTS before probing. This may reset Arduino-style boards.",
    )
    args = parser.parse_args()
    baudrates = (
        [int(item.strip()) for item in args.sweep.split(",") if item.strip()]
        if args.sweep
        else [args.baud]
    )
    if not baudrates:
        log("No baud rates selected")
        return 2
    fd = args.fd
    lib = ctypes.CDLL(LIBUSB)
    configure_libusb(lib)

    ctx = ctypes.c_void_p()
    try:
        lib.libusb_set_option(None, 2)
    except Exception:
        pass
    res = lib.libusb_init(ctypes.byref(ctx))
    log(f"libusb_init: {res}")
    if res != 0:
        return 1

    handle = ctypes.c_void_p()
    res = lib.libusb_wrap_sys_device(ctx, fd, ctypes.byref(handle))
    log(f"wrap fd {fd}: {res}")
    if res != 0:
        lib.libusb_exit(ctx)
        return 1

    try:
        if hasattr(lib, "libusb_set_auto_detach_kernel_driver"):
            log(f"auto_detach: {lib.libusb_set_auto_detach_kernel_driver(handle, 1)}")
        res = lib.libusb_claim_interface(handle, 0)
        log(f"claim interface 0: {res}")
        if res != 0:
            return 1

        log("initial read")
        bulk_read(lib, handle, 1)

        for baudrate in baudrates:
            reply = probe_baud(lib, handle, baudrate, dtr=args.dtr)
            if b"FIRMWARE_NAME" in reply or b"ok" in reply.lower():
                break

        lib.libusb_release_interface(handle, 0)
    finally:
        lib.libusb_close(handle)
        lib.libusb_exit(ctx)


if __name__ == "__main__":
    raise SystemExit(main())
