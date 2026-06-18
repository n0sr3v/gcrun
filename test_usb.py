import os
import sys
import ctypes

def test():
    print(f"Arguments: {sys.argv}")
    try:
        lib = ctypes.CDLL("/data/data/com.termux/files/usr/lib/libusb-1.0.so")
        print("libusb loaded successfully")
    except Exception as e:
        print(f"Failed to load libusb: {e}")
        return

    if len(sys.argv) < 2:
        print("No FD provided")
        return

    fd = int(sys.argv[1])
    print(f"Attempting to use FD: {fd}")
    
    # Init libusb context
    ctx = ctypes.c_void_p()
    # LIBUSB_OPTION_NO_DEVICE_DISCOVERY = 2
    try:
        lib.libusb_set_option(None, 2)
    except: pass
    
    res = lib.libusb_init(ctypes.byref(ctx))
    print(f"libusb_init res: {res}")
    
    if res == 0:
        handle = ctypes.c_void_p()
        res = lib.libusb_wrap_sys_device(ctx, fd, ctypes.byref(handle))
        print(f"libusb_wrap_sys_device res: {res}")
        if res == 0:
            print("SUCCESS: Device wrapped!")
            lib.libusb_close(handle)
        lib.libusb_exit(ctx)

if __name__ == "__main__":
    test()
