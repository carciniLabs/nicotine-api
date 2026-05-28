
import sys
import os
sys.path.insert(0, "/home/crab/.local/lib/python3.12/site-packages")
from pynicotine.core import Core

def inspect_core():
    core = Core()
    print("Attributes of Core:")
    for attr in dir(core):
        if not attr.startswith('_'):
            print(f"- {attr}")

if __name__ == "__main__":
    inspect_core()
