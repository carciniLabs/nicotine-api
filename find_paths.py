
import sys
import os
sys.path.insert(0, "/home/crab/.local/lib/python3.12/site-packages")
from pynicotine.core import Core

def find_paths():
    core = Core()
    print(f"Config path: {core.config.path}")
    print(f"Data path: {core.settings.userdata_path}")

if __name__ == "__main__":
    find_paths()
