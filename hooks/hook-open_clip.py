# hooks/hook-open_clip.py
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files('open_clip')
hiddenimports = collect_submodules('open_clip')