import os
import sys

fd = int(sys.argv[1])
print(f"Checking FD with lseek: {fd}")
try:
    try:
        os.lseek(fd, 0, 0)
    except Exception as se:
        print(f"Seek failed (expected for character device): {se}")
    data = os.read(fd, 18)
    print(f"Data length: {len(data)}")
    print(f"Data hex: {data.hex()}")
except Exception as e:
    print(f"Error: {e}")
