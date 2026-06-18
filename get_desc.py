with open("/dev/bus/usb/001/002", "rb") as f:
    print(f.read(18).hex())
