# Building AESTHETIC

Complete instructions for building the Windows installer, macOS DMG, and Linux Docker image.

---

## Windows installer

### Prerequisites

Install these once:

- **Inno Setup 6** — https://jrsoftware.org/isdl.php
- **PyInstaller** — `pip install pyinstaller` (in the venv)
- **ffmpeg static build for Windows** — https://github.com/BtbN/FFmpeg-Builds/releases
  - Download `ffmpeg-master-latest-win64-gpl.zip`
  - Extract `ffmpeg.exe` and `ffprobe.exe` into `build\ffmpeg\`

### First-time setup

```
build\
├── ffmpeg\
│   ├── ffmpeg.exe       ← download and place here
│   └── ffprobe.exe      ← download and place here
├── assets\
│   └── aesthetic_logo.ico   ← convert aesthetic_logo_png.png to ICO
├── hooks\
│   ├── hook-webview.py
│   ├── hook-ultralytics.py
│   └── hook-open_clip.py
├── installer.iss
└── build_windows.ps1
```

Convert the PNG logo to ICO (run once):
```powershell
python -c "
from PIL import Image
img = Image.open('aesthetic_logo_png.png')
img.save('build/assets/aesthetic_logo.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(256,256)])
"
```

### Build

```powershell
cd E:\AestheticApp
.venv\Scripts\Activate.ps1
.\build\build_windows.ps1
```

Optional parameters:
```powershell
# specify version
.\build\build_windows.ps1 -Version "1.0.1"

# skip PyInstaller (re-run Inno Setup only)
.\build\build_windows.ps1 -SkipPyInstaller

# clean before building
.\build\build_windows.ps1 -Clean
```

### Output

```
dist\
├── AESTHETIC\               ← PyInstaller bundle (for testing)
│   ├── AESTHETIC.exe
│   ├── ffmpeg.exe
│   ├── ffprobe.exe
│   └── ...
└── installer\
    └── AESTHETIC-Setup-1.0.0.exe   ← distributable installer
```

Test the bundle before running Inno Setup:
```powershell
dist\AESTHETIC\AESTHETIC.exe
```

### What the installer does

1. Checks for Microsoft WebView2 runtime — downloads and installs if missing
2. Installs the application to `%ProgramFiles%\AESTHETIC\`
3. Creates Start Menu shortcut and optional desktop icon
4. Creates user data directories in `%LOCALAPPDATA%\AESTHETIC\data\`
5. Offers to launch the app after installation

### Uninstalling

Standard Windows add/remove programs. User data in `%LOCALAPPDATA%\AESTHETIC\` is preserved (jobs, baseline, outputs). Only the application files are removed.

---

## Bundle size expectations

| Build type | Approximate size |
|---|---|
| CPU-only torch | ~800MB bundle, ~500MB installer |
| CUDA torch (cu128) | ~4GB bundle, ~2.5GB installer |

The CUDA build is large because torch ships ~3GB of CUDA kernels and libraries. There is no way to reduce this significantly without switching to ONNX runtime (future work).

---

## macOS DMG

*Coming in a future build phase.*

Requirements will be:
- Apple Developer account (for code signing)
- Xcode command line tools
- `create-dmg` utility

---

## Linux Docker

*Coming in a future build phase.*

The Docker version runs the bridge as an HTTP API server instead of using pywebview, allowing headless operation. The UI is served on `localhost:8080`.

---

## Troubleshooting

**`ModuleNotFoundError` for aesthetic modules**
PyInstaller missed a hidden import. Add it to `hiddenimports` in `aesthetic.spec` and rebuild.

**WebView2 not loading**
The WebView2 runtime must be installed. The installer handles this automatically. Manual install: https://developer.microsoft.com/en-us/microsoft-edge/webview2/

**ffmpeg not found at runtime**
`ffmpeg.exe` must be in the same directory as `AESTHETIC.exe`. The build script handles this — check that `build\ffmpeg\ffmpeg.exe` exists before building.

**CUDA errors**
If the user doesn't have an NVIDIA GPU or CUDA drivers, the app falls back to CPU automatically. CUDA errors in the console are non-fatal.

**`WinError 193` on cublas DLL**
The torch CUDA build is incompatible with the installed CUDA driver. The user needs to update their NVIDIA drivers. The app will still work in CPU mode.
