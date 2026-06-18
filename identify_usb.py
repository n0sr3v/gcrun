import os
import sys
import usb.core
import usb.backend.libusb1
import ctypes

def identify():
    if len(sys.argv) < 2:
        print("Usage: termux-usb -e 'python3 identify_usb.py' /dev/bus/usb/xxx/yyy")
        return

    try:
        fd = int(sys.argv[1])
    except ValueError:
        print(f"Invalid FD: {sys.argv[1]}")
        return

    print(f"Using File Descriptor: {fd}")

    # Manually load libusb
    lib_path = "/data/data/com.termux/files/usr/lib/libusb-1.0.so"
    lib = ctypes.CDLL(lib_path)

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
    lib.libusb_get_device.argtypes = [ctypes.c_void_p]
    lib.libusb_get_device.restype = ctypes.c_void_p
    lib.libusb_close.argtypes = [ctypes.c_void_p]
    lib.libusb_close.restype = None
    lib.libusb_exit.argtypes = [ctypes.c_void_p]
    lib.libusb_exit.restype = None
    
    # Initialize libusb with NO_DEVICE_DISCOVERY
    # According to libusb.h: LIBUSB_OPTION_NO_DEVICE_DISCOVERY = 2
    LIBUSB_OPTION_NO_DEVICE_DISCOVERY = 2
    
    # Note: libusb_init should be called BEFORE libusb_set_option in some versions,
    # or it might take NULL for context to set global option.
    
    ctx = ctypes.c_void_p()
    # Newer libusb might require setting the option on the context or NULL
    try:
        lib.libusb_set_option(None, LIBUSB_OPTION_NO_DEVICE_DISCOVERY)
    except:
        pass

    res = lib.libusb_init(ctypes.byref(ctx))
    if res != 0:
        print(f"libusb_init failed: {res}")
        # Try again WITHOUT setting option first
        res = lib.libusb_init(ctypes.byref(ctx))
        if res != 0:
             print(f"Retry libusb_init failed: {res}")
             return
    
    handle = ctypes.c_void_p()
    res = lib.libusb_wrap_sys_device(ctx, fd, ctypes.byref(handle))
    
    if res != 0:
        print(f"Failed to wrap device: error {res}")
        return

    dev_ptr = lib.libusb_get_device(handle)
    
    class usb_device_descriptor(ctypes.Structure):
        _fields_ = [
            ("bLength", ctypes.c_uint8),
            ("bDescriptorType", ctypes.c_uint8),
            ("bcdUSB", ctypes.c_uint16),
            ("bDeviceClass", ctypes.c_uint8),
            ("bDeviceSubClass", ctypes.c_uint8),
            ("bDeviceProtocol", ctypes.c_uint8),
            ("bMaxPacketSize0", ctypes.c_uint8),
            ("idVendor", ctypes.c_uint16),
            ("idProduct", ctypes.c_uint16),
            ("bcdDevice", ctypes.c_uint16),
            ("iManufacturer", ctypes.c_uint8),
            ("iProduct", ctypes.c_uint8),
            ("iSerialNumber", ctypes.c_uint8),
            ("bNumConfigurations", ctypes.c_uint8),
        ]

    desc = usb_device_descriptor()
    lib.libusb_get_device_descriptor.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(usb_device_descriptor),
    ]
    lib.libusb_get_device_descriptor.restype = ctypes.c_int
    res = lib.libusb_get_device_descriptor(dev_ptr, ctypes.byref(desc))
    if res != 0:
        print(f"Failed to read descriptor: error {res}")
        return
    
    print(f"VENDOR ID:  {hex(desc.idVendor)}")
    print(f"PRODUCT ID: {hex(desc.idProduct)}")
    
    lib.libusb_close(handle)
    lib.libusb_exit(ctx)

if __name__ == "__main__":
    identify()
