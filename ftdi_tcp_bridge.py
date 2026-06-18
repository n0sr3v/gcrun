import os
import sys
import socket
import select
import ctypes
import time
import argparse

BAUDRATE_REF_BASE = 3000000
FRAC_DIV_CODE = (0, 3, 2, 4, 1, 5, 6, 7)

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

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

def strip_ftdi_status(raw):
    payload = bytearray()
    for offset in range(0, len(raw), 64):
        packet = raw[offset : offset + 64]
        if len(packet) > 2:
            payload.extend(packet[2:])
    return bytes(payload)

def run_bridge():
    log("Bridge script entry point")
    parser = argparse.ArgumentParser(description="Termux native FTDI TCP bridge.")
    parser.add_argument("fd", type=int, help="USB file descriptor passed by termux-usb")
    parser.add_argument("--baud", type=int, default=250000, help="Serial baud rate.")
    parser.add_argument("--host", default="127.0.0.1", help="TCP listen host.")
    parser.add_argument("--port", type=int, default=8888, help="TCP listen port.")
    args = parser.parse_args()
    fd = args.fd

    log(f"Initializing libusb with FD={fd}...")
    try:
        lib = ctypes.CDLL("/data/data/com.termux/files/usr/lib/libusb-1.0.so")
        configure_libusb(lib)
        log("libusb binary loaded")
    except Exception as e:
        log(f"Failed to load libusb: {e}")
        return

    ctx = ctypes.c_void_p()
    # NO_DEVICE_DISCOVERY = 2
    try:
        lib.libusb_set_option(None, 2)
        log("Option NO_DEVICE_DISCOVERY set")
    except:
        log("Warning: libusb_set_option not available")

    res = lib.libusb_init(ctypes.byref(ctx))
    log(f"libusb_init res: {res}")
    if res != 0: return

    handle = ctypes.c_void_p()
    res = lib.libusb_wrap_sys_device(ctx, fd, ctypes.byref(handle))
    log(f"libusb_wrap_sys_device res: {res}")
    if res != 0: return

    log("Attempting to claim interface 0...")
    try:
        # Some versions might not have this
        lib.libusb_set_auto_detach_kernel_driver(handle, 1)
        log("Auto-detach enabled")
    except:
        log("Auto-detach not supported")

    res = lib.libusb_claim_interface(handle, 0)
    log(f"libusb_claim_interface res: {res}")
    if res != 0:
        lib.libusb_close(handle)
        lib.libusb_exit(ctx)
        return

    actual_baud, baud_value, baud_index = convert_baudrate(args.baud)
    log(
        f"Configuring FTDI for requested baud {args.baud}, "
        f"actual {actual_baud}, 8N1..."
    )
    # Purge RX/TX, set baud, then 8 data bits/no parity/1 stop bit.
    for request, value, index, label in (
        (0, 1, 0, "purge rx"),
        (0, 2, 0, "purge tx"),
        (3, baud_value, baud_index, "baud"),
        (4, 8, 0, "line format"),
    ):
        res = lib.libusb_control_transfer(handle, 0x40, request, value, index, None, 0, 1000)
        log(f"FTDI {label} control transfer res: {res}")
        if res < 0:
            lib.libusb_release_interface(handle, 0)
            lib.libusb_close(handle)
            lib.libusb_exit(ctx)
            return

    log(f"Setting up TCP server on {args.host}:{args.port}...")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(1)
    server.setblocking(False)
    log("SERVER READY - Listening for connections")

    clients = []
    try:
        while True:
            # TCP Connections
            try:
                client, addr = server.accept()
                log(f"New TCP client: {addr}")
                client.setblocking(False)
                clients.append(client)
            except BlockingIOError: pass

            # USB -> TCP
            buf = ctypes.create_string_buffer(512)
            transferred = ctypes.c_int()
            res = lib.libusb_bulk_transfer(handle, 0x81, buf, 512, ctypes.byref(transferred), 1)
            if res == 0 and transferred.value > 2:
                data = strip_ftdi_status(buf.raw[:transferred.value])
                for c in clients:
                    try: c.sendall(data)
                    except: clients.remove(c)

            # TCP -> USB
            for c in clients:
                try:
                    data = c.recv(1024)
                    if data:
                        log(f"TCP -> USB: {repr(data)}")
                        w_transferred = ctypes.c_int()
                        res = lib.libusb_bulk_transfer(handle, 0x02, data, len(data), ctypes.byref(w_transferred), 100)
                        if res != 0: log(f"USB Write Error: {res}")
                    else:
                        log("TCP client disconnected")
                        clients.remove(c)
                except BlockingIOError: pass
                except: clients.remove(c)

            time.sleep(0.001)
    except KeyboardInterrupt:
        log("Shutting down...")
    finally:
        lib.libusb_release_interface(handle, 0)
        lib.libusb_close(handle)
        lib.libusb_exit(ctx)
        server.close()

if __name__ == "__main__":
    run_bridge()
