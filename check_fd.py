import os
import sys

# Print arguments and environment to see where the FD is
print(f"Arguments: {sys.argv}")
print(f"TERMUX_USB_FD: {os.environ.get('TERMUX_USB_FD')}")

fd_str = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('TERMUX_USB_FD')

if fd_str:
    try:
        fd = int(fd_str)
        print(f"Trying to read from FD: {fd}")
        with os.fdopen(fd, "rb", closefd=False) as f:
            print(f"Descriptor Hex: {f.read(18).hex()}")
    except Exception as e:
        print(f"Error reading from FD: {e}")
else:
    print("No FD found in arguments or environment.")
