@echo off
setlocal EnableExtensions
set MSG=%*
if "%MSG%"=="" (
  echo Usage: commit_msg.cmd "Your commit message"
  exit /b 1
)
echo %MSG%> .gitmessage.txt
git commit -F .gitmessage.txt
del .gitmessage.txt
