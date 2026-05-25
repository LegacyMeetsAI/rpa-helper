@echo off
rem RPA Helper 打包脚本（.bat 版）：调用 PyInstaller + 内嵌 Chromium。
rem Author: huaiqing.wang
setlocal
cd /d "%~dp0\.."

echo Installing slim packaging requirements...
py -m pip install -r requirements-packaging.txt
if errorlevel 1 exit /b %errorlevel%

taskkill /IM RPAHelper.exe /F >nul 2>nul

if exist build rmdir /S /Q build
if exist dist rmdir /S /Q dist

py -m PyInstaller --noconfirm RPAHelper.spec
if errorlevel 1 exit /b %errorlevel%

if not exist dist\RPAHelper\config mkdir dist\RPAHelper\config
if not exist dist\RPAHelper\logs mkdir dist\RPAHelper\logs

powershell -ExecutionPolicy Bypass -File "%~dp0_bundle_chromium.ps1"
if errorlevel 1 exit /b %errorlevel%

powershell -ExecutionPolicy Bypass -File "%~dp0_slim_build.ps1"
if errorlevel 1 exit /b %errorlevel%

echo Build complete: dist\RPAHelper\RPAHelper.exe
