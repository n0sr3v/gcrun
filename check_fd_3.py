import os
import sys

fd = int(sys.argv[1])
print(f"Checking FD via os.read: {fd}")
try:
    data = os.read(fd, 18)
    print(f"Data length: {len(data)}")
    print(f"Data hex: {data.hex()}")
except Exception as e:
    print(f"Error: {e}")
