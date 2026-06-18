import os
import sys
import socket
import select
import ctypes
from pyftdi.ftdi import Ftdi

def run_bridge():
    if len(sys.argv) < 2:
        print("Usage: termux-usb -e 'python3 bridge_ftdi.py' /dev/bus/usb/xxx/yyy")
        return

    try:
        fd = int(sys.argv[1])
    except ValueError:
        print(f"Invalid FD: {sys.argv[1]}")
        return

    print(f"Starting FTDI bridge on FD: {fd}")

    # 1. Initialize PyFtdi using the FD
    ftdi = Ftdi()
    
    # We need to reach into the backend to wrap the FD
    # This is a bit hacky but it's the only way on Android
    from usb.backend.libusb1 import _LibUSB, _load_library
    lib_path = "/data/data/com.termux/files/usr/lib/libusb-1.0.so"
    lib = ctypes.CDLL(lib_path)
    
    # Initialize libusb without discovery
    LIBUSB_OPTION_NO_DEVICE_DISCOVERY = 2
    try:
        lib.libusb_set_option(None, LIBUSB_OPTION_NO_DEVICE_DISCOVERY)
    except:
        pass
        
    ctx = ctypes.c_void_p()
    lib.libusb_init(ctypes.byref(ctx))
    
    usb_handle = ctypes.c_void_p()
    res = lib.libusb_wrap_sys_device(ctx, fd, ctypes.byref(usb_handle))
    if res != 0:
        print(f"Failed to wrap USB device: {res}")
        return

    # Now we have a libusb handle, we need to tell PyFtdi to use it.
    # PyFtdi uses PyUSB, which doesn't easily accept raw handles.
    # HOWEVER, we can manually open the FTDI device if we know the details.
    
    try:
        # We'll use the low-level Ftdi.open_mpsse or similar
        # But wait, we can just use the handle directly if we patch Ftdi
        
        # Simplest: Use the FD to get Vendor/Product, then use PyFtdi's 
        # ability to open a device by its USB handle.
        # Actually, let's just use the ftdi.open_import(usb_handle) if it exists
        # In pyftdi 0.57+, we might need to manually construct the UsbDevice
        
        print("Opening FTDI device...")
        # For now, let's try the most direct path:
        ftdi.open_bitbang_from_url(f'ftdi://0x0403:0x6001/1') 
        # ^ This will fail because it tries to find the device again.
    except Exception as e:
        print(f"Standard open failed (expected): {e}")

    # --- THE REAL FIX: Manual initialization of the FTDI chip ---
    # Since we can't easily make PyFtdi use our FD, 
    # we'll use a simpler TCP-to-USB-Raw bridge for now if that's easier,
    # OR we use the 'socat' bridge which is more 'native'.
    
    print("Bridge script is ready to be refined. Let's try the SOCAT approach first as it is more robust.")

if __name__ == "__main__":
    run_bridge()
