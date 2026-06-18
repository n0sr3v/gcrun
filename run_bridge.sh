#!/data/data/com.termux/files/usr/bin/bash
# Use absolute paths for everything in termux-usb -e
cd /data/data/com.termux/files/home/gcrun
/data/data/com.termux/files/usr/bin/python3 ftdi_tcp_bridge.py "$1" > bridge.log 2>&1
