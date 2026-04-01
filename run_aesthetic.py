# run_aesthetic.py
#
# PyInstaller entry point — lives at repo root so it has no parent package.
# Bootstraps the aesthetic package and calls main().
# Do NOT use relative imports here.

import sys
import os
from pathlib import Path
import multiprocessing

# freeze_support MUST be the first thing called in a PyInstaller bundle
# that uses multiprocessing — before any other imports
multiprocessing.freeze_support()

# When frozen, sys._MEIPASS contains the bundle root.
# Add it to sys.path so 'import aesthetic' works.
if getattr(sys, "frozen", False):
    bundle_dir = Path(sys._MEIPASS)
    if str(bundle_dir) not in sys.path:
        sys.path.insert(0, str(bundle_dir))
    # add exe directory to PATH so bundled ffmpeg/ffprobe are found
    exe_dir = Path(sys.executable).parent
    os.environ["PATH"] = str(exe_dir) + os.pathsep + os.environ.get("PATH", "")

from aesthetic.app import main

if __name__ == "__main__":
    main()
