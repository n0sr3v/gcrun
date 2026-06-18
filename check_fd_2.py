import os
import sys

fd = int(sys.argv[1])
print(f"Checking FD: {fd}")
try:
    # Try reading byte by byte
    with os.fdopen(fd, "rb", closefd=False) as f:
        data = f.read(18)
        print(f"Data length: {len(data)}")
        print(f"Data hex: {data.hex()}")
except Exception as e:
    print(f"Error: {e}")
