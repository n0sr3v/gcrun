# Session Summary: CNC Jog Control on Android Termux
**Date:** 2026-03-19
**Project:** CNC Web Jog Interface for RAMPS 1.4 / Arduino Mega

## 🎯 General Goal
The objective is to run a web-based G-code sender and CNC jog interface directly on an Android device using Termux. This setup allows a phone/tablet connected via USB OTG to control a RAMPS 1.4 (Marlin) based CNC machine without requiring a PC.

## 🚧 Challenges & Struggles
1.  **Android Device Access**: Modern Android (15/16) strictly blocks access to `/dev/ttyUSB0` or `/dev/ttyACM0`. Standard serial libraries like `pySerial` cannot see the hardware directly.
2.  **Permission Popups**: Using the native `termux-usb` tool requires handling Android system popups and passing file descriptors (FD) to background processes, which proved unstable for long-running scripts.
3.  **Library Compatibility**:
    *   `pySerial`'s `list_ports` module crashes on Android because it doesn't know how to enumerate devices.
    *   Flask's `debug=True` mode uses `multiprocessing`, which is partially broken in Termux, causing silent server crashes.
4.  **Hardware Identification**: Identifying the USB-to-Serial chipset was difficult without `lsusb`, but eventually confirmed as an **FTDI FT232R**.

## ✅ Accomplishments So Far
1.  **Hardware Identification**: Successfully used a custom Python script to wrap the USB file descriptor and read the device descriptor, identifying the FTDI chip.
2.  **Architecture Shift**: Moved from a fragile "Native Termux" bridge to a robust **TCP Bridge** model. 
    *   The user installed the **"USB Serial Console"** app to handle the heavy lifting of Android USB drivers.
    *   This app acts as a bridge, exposing the Arduino's serial data on a local TCP port (e.g., `8080`).
3.  **App Fixes**:
    *   Modified `app.py` to use `serial.serial_for_url()` instead of `serial.Serial()`, allowing it to connect to network sockets.
    *   Wrapped failing `list_ports` calls in `try-except` blocks to prevent server crashes.
    *   Disabled Flask's reloader/debug mode to ensure stability on the Termux Python runtime.
4.  **Frontend Improvements**:
    *   Fixed a Rendering/CSS bug on the `<canvas>` element.
    *   Added a manual port input field to the web UI so users can easily type `socket://127.0.0.1:8080` if the dropdown isn't populated.

## 📍 Current Status
*   **Web App**: Running in the background on `http://localhost:5000`.
*   **Connection Method**: User connects via the **USB Serial Console** app, starts its TCP Server, and then connects the web app to that socket.
*   **Result**: The application is online and reachable, with the "Connected" state achieved via the bridge.
