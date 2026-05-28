
import sys
import os
from pynicotine.core import Core

def test_core():
    try:
        core = Core()
        print("Core initialized")
        print(f"Username: {core.config.sections['server']['username']}")
        print(f"Connected: {core.slsknet.connected}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_core()
