
import sys
import os
import time
import threading
import json

sys.path.insert(0, "/home/crab/.local/lib/python3.12/site-packages")
from pynicotine.core import Core
from pynicotine.events import events

def on_event(event, *args):
    try:
        print(f"EVENT: {event} | ARGS: {args[:3]}...")
    except:
        pass

def monitor():
    core = Core()
    core.init_components()
    
    # Connect to all events (if possible) or just common ones
    # Actually, events.events is a dict of event names to observers
    for event_name in events.events.keys():
        events.connect(event_name, lambda *args, en=event_name: on_event(en, *args))
    
    print("Starting core...")
    core.start()
    
    time.sleep(5)
    print("Performing search...")
    core.search.do_search("Warlung", 0)
    
    # Wait for results
    time.sleep(20)
    core.quit()

if __name__ == "__main__":
    monitor()
