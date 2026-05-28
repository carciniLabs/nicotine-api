
import sys
import os
import json
import time
import threading

# Path to Nicotine+ library
# Try common pynicotine install locations
NICOTINE_LIBS = [
    os.path.expanduser("~/.local/lib/python3.12/site-packages"),
    "/usr/lib/python3.12/site-packages",
    "/usr/share/nicotine/pynicotine",
]
for lib in NICOTINE_LIBS:
    if os.path.exists(lib) and lib not in sys.path:
        sys.path.insert(0, lib)

try:
    from pynicotine.core import core
    from pynicotine.events import events
    from pynicotine.config import config
except ImportError as e:
    print(json.dumps({"type": "error", "message": f"pynicotine not found: {e}"}))
    sys.exit(1)

class NicotineBridge:
    def __init__(self):
        self.core = core
        self.running = True
        self.search_results = {}
        self.lock = threading.Lock()
        self.connected = threading.Event()
        self.search_callbacks = {}  # token -> {"event": threading.Event}

    def on_search_response(self, msg):
        try:
            username = getattr(msg, 'search_username', None) or getattr(msg, 'username', 'unknown')
            token = getattr(msg, 'token', 0)

            # Skip if token was cleared by pynicotine's internal filter
            if token is None:
                sys.stderr.write(f"DEBUG: search response skipped (token=None)\n")
                return

            results = getattr(msg, 'list', None) or []
            sys.stderr.write(f"DEBUG: search response token={token}, results={len(results)}\n")

            # Per-peer fields from the search response message
            inqueue = getattr(msg, 'inqueue', 0)
            freeulslots = getattr(msg, 'freeulslots', False)
            # If peer has free slots, queue length is 0; otherwise use reported value (ensure >= 1)
            queue_length = 0 if freeulslots else (inqueue or 1)
            ulspeed = getattr(msg, 'ulspeed', 0)

            formatted = []
            for r in results:
                if r is None:
                    continue

                # Result tuple from pynicotine 3.3.x: (code, filename, size, ext, attrs)
                # attrs is a dict keyed by FileAttribute enum (0=BITRATE, 1=DURATION, etc.)
                if isinstance(r, (list, tuple)) and len(r) >= 5:
                    raw_attrs = r[4]
                    attrs = raw_attrs if isinstance(raw_attrs, dict) else {}
                elif isinstance(r, (list, tuple)) and len(r) >= 3:
                    attrs = {}
                elif isinstance(r, dict):
                    # Dict-style result — extract fields by key
                    formatted.append({
                        "filename": r.get("filename", r.get("name", "")),
                        "size": r.get("size", 0),
                        "user": username,
                        "speed": ulspeed,
                        "queue_length": queue_length,
                        "bitrate": r.get("bitrate", ""),
                        "duration": r.get("duration", 0)
                    })
                    continue
                else:
                    continue
                # attrs is guaranteed to be a dict here; .get() is always safe
                formatted.append({
                    "filename": r[1],
                    "size": r[2],
                    "user": username,
                    "speed": ulspeed,
                    "queue_length": queue_length,
                    "bitrate": attrs.get(0, ""),
                    "duration": attrs.get(1, 0)
                })

            if not formatted:
                return

            # Cap results per message to avoid overwhelming the Node.js pipe
            MAX_RESULTS_PER_MSG = 200
            if len(formatted) > MAX_RESULTS_PER_MSG:
                formatted = formatted[:MAX_RESULTS_PER_MSG]

            with self.lock:
                if token not in self.search_results:
                    self.search_results[token] = []
                self.search_results[token].extend(formatted)

            print(json.dumps({"type": "search_results", "token": token, "data": formatted}, default=str), flush=True)
        except Exception as e:
            import traceback
            sys.stderr.write(f"Error processing search response: {e}\n")
            traceback.print_exc(file=sys.stderr)

    def on_server_login(self, msg):
        """Handle login success/failure from pynicotine."""
        try:
            if msg.success:
                self.connected.set()
                print(json.dumps({
                    "type": "connected",
                    "username": config.sections["server"]["login"],
                }), flush=True)
            else:
                reason = getattr(msg, "reason", "unknown")
                print(json.dumps({"type": "error", "message": f"Login failed: {reason}"}), flush=True)
        except Exception:
            import traceback
            sys.stderr.write(f"Login handler error:\n{traceback.format_exc()}\n")

    def on_server_disconnect(self, _msg):
        """Handle disconnection from pynicotine."""
        self.connected.clear()
        print(json.dumps({"type": "disconnected"}), flush=True)

    def setup(self):
        # Let pynicotine use its XDG defaults:
        #   config_file_path -> ~/.config/nicotine/config  (credentials live here)
        #   data_folder_path -> ~/.local/share/nicotine    (downloads, logs, shares dbs)
        # Previously called set_data_folder("~/.config/nicotine+") which pointed
        # NICOTINE_DATA_HOME at the wrong dir and broke ${NICOTINE_DATA_HOME} path
        # resolution in the config file.
        
        enabled = {
            "error_handler", "signal_handler", "portmapper", "network_thread", "shares", "users",
            "notifications", "network_filter", "now_playing", "statistics", "update_checker",
            "search", "downloads", "uploads", "interests", "userbrowse", "userinfo", "buddies",
            "chatrooms", "privatechat", "pluginhandler"
        }
        self.core.init_components(enabled_components=enabled)
        config.load_config()
        
        events.connect("file-search-response", self.on_search_response)
        events.connect("server-login", self.on_server_login)
        events.connect("server-disconnect", self.on_server_disconnect)
        
        print(json.dumps({"type": "ready"}), flush=True)
        
        try:
            self.core.start()
        except Exception as e:
            sys.stderr.write(f"Core start failed: {e}\n")
        
        if config.sections["server"]["login"]:
            try:
                self.core.connect()
            except Exception as e:
                sys.stderr.write(f"Core connect failed: {e}\n")

    def run_loop(self):
        while self.running:
            try:
                if not events.process_thread_events():
                    break
            except Exception as e:
                sys.stderr.write(f"Event loop error: {e}\n")
            time.sleep(0.1)

    def cmd_loop(self):
        for line in sys.stdin:
            try:
                line = line.strip()
                if not line: continue
                req = json.loads(line)
                method = req.get("method")
                params = req.get("params", {})
                
                if method == "search":
                    query = params.get("query")
                    self.core.search.do_search(query, "global")
                    token = self.core.search.token
                    print(json.dumps({"type": "search_ack", "token": token}), flush=True)
                
                elif method == "download":
                    user = params.get("user")
                    filename = params.get("filename")
                    self.core.downloads.enqueue_download(user, filename)
                    print(json.dumps({"type": "download_ack", "user": user, "file": filename}), flush=True)
                
                elif method == "downloads":
                    res = []
                    if self.core.downloads:
                        for t in self.core.downloads.transfers.values():
                            res.append({
                                "id": t.token,
                                "user": t.username,
                                "filename": t.virtual_path,
                                "status": t.status,
                                "size": t.size,
                                "progress": t.current_byte_offset,
                                "speed_kbps": round(t.speed / 1024, 1) if t.speed else 0,
                            })
                    print(json.dumps({"type": "downloads", "data": res}, default=str), flush=True)

                elif method == "rescan":
                    if self.core.shares:
                        self.core.shares.rescan_shares()
                        print(json.dumps({"type": "rescan_ack"}), flush=True)

                elif method == "status":
                    # Server field: config stores (host, port) tuple, spec wants "host:port" string
                    server_val = config.sections.get("server", {}).get("server", "")
                    if isinstance(server_val, (list, tuple)) and len(server_val) == 2:
                        server_str = f"{server_val[0]}:{server_val[1]}"
                    else:
                        server_str = str(server_val)

                    # Listening port: config stores (low, high) tuple, take first value
                    portrange = config.sections.get("server", {}).get("portrange", (0, 0))
                    listening_port = portrange[0] if isinstance(portrange, (list, tuple)) else portrange

                    # Downloads dir: resolve ${NICOTINE_DATA_HOME} template if present
                    downloaddir = config.sections.get("transfers", {}).get("downloaddir", "")
                    if "${NICOTINE_DATA_HOME}" in str(downloaddir):
                        downloaddir = str(downloaddir).replace("${NICOTINE_DATA_HOME}", config.data_folder_path)
                    # Fallback to environment variable or sensible default
                    if not downloaddir or not os.path.exists(downloaddir):
                        downloaddir = os.environ.get("SLSK_DOWNLOAD_DIR", "~/Downloads/slsk")

                    shares_count = 0
                    try:
                        shares_count = len(config.sections.get("transfers", {}).get("shared", []))
                    except Exception:
                        pass

                    stats = {
                        "connected": self.connected.is_set(),
                        "username": config.sections.get("server", {}).get("login", ""),
                        "server": server_str,
                        "listening_port": listening_port,
                        "shares": shares_count,
                        "downloads_dir": downloaddir,
                    }
                    
                    print(json.dumps({"type": "status", "data": stats}, default=str), flush=True)

                elif method == "cancel_download":
                    transfer_id = params.get("id", "")
                    found = False
                    if self.core.downloads and transfer_id:
                        for key, t in self.core.downloads.transfers.items():
                            # Match by token (active transfer) or key (username+virtual_path)
                            if str(t.token) == transfer_id or key == transfer_id:
                                self.core.downloads._abort_transfer(t)
                                print(json.dumps({
                                    "type": "cancel_download_ack",
                                    "id": transfer_id,
                                    "user": t.username,
                                    "filename": t.virtual_path,
                                }, default=str), flush=True)
                                found = True
                                break
                    if not found:
                        print(json.dumps({
                            "type": "cancel_download_ack",
                            "id": transfer_id,
                            "error": "Download not found",
                        }), flush=True)

                elif method == "shares":
                    shared_folders = config.sections.get("transfers", {}).get("shared", [])
                    buddy_shared = config.sections.get("transfers", {}).get("buddyshared", [])
                    trusted_shared = config.sections.get("transfers", {}).get("trustedshared", [])
                    
                    shares = []
                    for entry in shared_folders:
                        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                            shares.append({"name": entry[0], "path": entry[1], "type": "public"})
                        elif isinstance(entry, str):
                            shares.append({"name": entry, "path": entry, "type": "public"})
                    for entry in buddy_shared:
                        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                            shares.append({"name": entry[0], "path": entry[1], "type": "buddy"})
                        elif isinstance(entry, str):
                            shares.append({"name": entry, "path": entry, "type": "buddy"})
                    for entry in trusted_shared:
                        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                            shares.append({"name": entry[0], "path": entry[1], "type": "trusted"})
                        elif isinstance(entry, str):
                            shares.append({"name": entry, "path": entry, "type": "trusted"})
                    
                    print(json.dumps({"type": "shares", "data": shares}), flush=True)

                elif method == "exit":
                    self.running = False
                    self.core.quit()
                    break

            except Exception as e:
                sys.stderr.write(f"Command error: {e}\n")

if __name__ == "__main__":
    bridge = NicotineBridge()
    bridge.setup()
    
    t = threading.Thread(target=bridge.cmd_loop, daemon=True)
    t.start()
    
    bridge.run_loop()
