"""Locate the selected installation or the checkout's native development build."""
import os
from pathlib import Path
import shutil


def default_binary():
    selected = os.environ.get('INKBOLT_EXE')
    if selected:
        return Path(selected).resolve()
    name = 'inkbolt.exe' if os.name == 'nt' else 'inkbolt'
    development = Path(__file__).resolve().parents[1] / 'target' / 'debug' / name
    if development.is_file():
        return development
    installed = shutil.which(name)
    return Path(installed) if installed else development
