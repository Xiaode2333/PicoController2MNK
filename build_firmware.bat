@echo off
setlocal
cd /d "%~dp0"
wsl.exe --cd "%~dp0" bash -lc "cmake -S . -B build -DPICO_SDK_FETCH_FROM_GIT=ON && cmake --build build --target pico_kbm_mapper -j"
if errorlevel 1 pause
