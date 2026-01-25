@echo off
set PY=C:\Users\fn.local\AppData\Local\Programs\Python\Python311\python.exe
if not exist "%PY%" set PY=C:\Users\fn.local\AppData\Local\Programs\Python\Python311\python.exe
%PY% app.py > server.log 2>&1
