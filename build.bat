@echo off
REM build.bat — AESTHETIC Windows x64 build script
REM
REM Run from the AestheticApp root with the venv activated:
REM   .venv\Scripts\Activate.ps1
REM   .\build.bat
REM
REM Output: dist\AESTHETIC\AESTHETIC.exe

echo ==========================================
echo  AESTHETIC — Windows x64 Build
echo ==========================================
echo.

REM Check pyinstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller --quiet
)

REM Check ffmpeg is available
if not exist "tools\ffmpeg.exe" (
    echo.
    echo WARNING: tools\ffmpeg.exe not found.
    echo Download from https://www.gyan.dev/ffmpeg/builds/
    echo Extract ffmpeg.exe to tools\ffmpeg.exe before distributing.
    echo The app will fall back to any system ffmpeg on PATH.
    echo.
)

REM Clean previous build
echo Cleaning previous build...
if exist "dist\AESTHETIC" rmdir /s /q "dist\AESTHETIC"
if exist "build\AESTHETIC"  rmdir /s /q "build\AESTHETIC"

REM Run PyInstaller
echo Running PyInstaller...
pyinstaller AESTHETIC.spec --noconfirm

if errorlevel 1 (
    echo.
    echo BUILD FAILED — check output above for errors.
    exit /b 1
)

echo.
echo ==========================================
echo  Build complete: dist\AESTHETIC\AESTHETIC.exe
echo ==========================================
echo.

REM Print size summary
for /f %%i in ('powershell -command "(Get-ChildItem dist\AESTHETIC -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB"') do (
    echo Bundle size: %%i MB
)

echo.
echo To run:  dist\AESTHETIC\AESTHETIC.exe
echo To distribute: zip dist\AESTHETIC\ folder
