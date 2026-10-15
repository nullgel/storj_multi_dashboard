#!/usr/bin/env python3
"""
Storj Multi-Node Summary Dashboard Server
A lightweight, zero-dependency Python server that aggregates statistics
from multiple Storj storage nodes and serves an interactive web dashboard.
"""

import sys
import os
import json
import time
import socket
import signal
from datetime import datetime, timezone
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("CONFIG_PATH", os.path.join(SCRIPT_DIR, "config.json"))
STATIC_DIR = os.path.join(SCRIPT_DIR, "static")

# In-memory cache
CACHE_DATA = None
CACHE_TIMESTAMP = 0
CACHE_TTL_SECONDS = 5  # Cache for 5s to prevent hammering nodes on multiple requests


def load_config():
    default_config = {
        "host": "0.0.0.0",
        "port": 8888,
        "poll_interval_seconds": 30,
        "nodes": []
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                default_config.update(cfg)
        except Exception as e:
            print(f"[WARN] Failed to load config from {CONFIG_PATH}: {e}")
    else:
        print(f"[INFO] Config not found at {CONFIG_PATH}, creating default...")
        save_config(default_config)
    return default_config


def save_config(cfg):
    try:
        parent_dir = os.path.dirname(os.path.abspath(CONFIG_PATH))
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save config to {CONFIG_PATH}: {e}")
        return False


def fetch_node_stats(node):
    ip = node.get("ip", "")
    port = node.get("port", 20909)
    name = node.get("name", f"Node ({ip})")
    node_id_cfg = node.get("id", f"node-{ip}")
    base_url = f"http://{ip}:{port}"

    result = {
        "id": node_id_cfg,
        "name": name,
        "ip": ip,
        "port": port,
        "dashboardUrl": base_url,
        "online": False,
        "error": None,
        "nodeID": None,
        "version": None,
        "upToDate": True,
        "quicStatus": None,
        "startedAt": None,
        "uptimeHours": 0,
        "lastPinged": None,
        "diskSpace": {
            "used": 0,
            "allocated": 0,
            "available": 0,
            "trash": 0,
            "reclaimable": 0,
            "overused": 0,
            "percentUsed": 0.0
        },
        "bandwidth": {
            "used": 0,
            "available": 0
        },
        "payout": {
            "current": {
                "payout": 0.0,
                "held": 0.0,
                "expected": 0.0,
                "egressBandwidth": 0,
                "egressRepairAudit": 0,
                "diskSpacePayout": 0.0
            },
            "previous": {
                "payout": 0.0,
                "held": 0.0,
                "egressBandwidth": 0,
                "egressRepairAudit": 0
            }
        },
        "audits": []
    }

    try:
        # 1. Main Node Info (/api/sno/)
        req_sno = urllib.request.Request(f"{base_url}/api/sno/", headers={"User-Agent": "StorjMultiDash/1.0"})
        with urllib.request.urlopen(req_sno, timeout=3.5) as resp:
            sno = json.loads(resp.read().decode("utf-8"))

        result["online"] = True
        result["nodeID"] = sno.get("nodeID")
        result["version"] = sno.get("version")
        result["upToDate"] = sno.get("upToDate", True)
        result["quicStatus"] = sno.get("quicStatus", "Unknown")
        result["startedAt"] = sno.get("startedAt")
        result["lastPinged"] = sno.get("lastPinged")

        # Calculate uptime
        if result["startedAt"]:
            try:
                # Format: 2026-10-08T17:16:39.760619083Z
                st = result["startedAt"][:19]
                dt = datetime.strptime(st, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                uptime_sec = (datetime.now(timezone.utc) - dt).total_seconds()
                result["uptimeHours"] = round(uptime_sec / 3600.0, 1)
            except Exception:
                pass

        disk = sno.get("diskSpace", {})
        used = disk.get("used", 0)
        allocated = disk.get("allocated", 0)
        pct = (used / allocated * 100.0) if allocated > 0 else 0.0

        result["diskSpace"] = {
            "used": used,
            "allocated": allocated,
            "available": disk.get("available", 0),
            "trash": disk.get("trash", 0),
            "reclaimable": disk.get("reclaimable", 0),
            "overused": disk.get("overused", 0),
            "percentUsed": round(pct, 1)
        }

        bw = sno.get("bandwidth", {})
        result["bandwidth"] = {
            "used": bw.get("used", 0),
            "available": bw.get("available", 0)
        }

        # 2. Estimated Payout (/api/sno/estimated-payout)
        # Note: Storj SNO API returns payout numbers in USD CENTS (e.g. 86.41 cents = $0.8641).
        # We divide by 100.0 to convert to USD dollars.
        try:
            req_payout = urllib.request.Request(f"{base_url}/api/sno/estimated-payout", headers={"User-Agent": "StorjMultiDash/1.0"})
            with urllib.request.urlopen(req_payout, timeout=3.5) as resp:
                payout = json.loads(resp.read().decode("utf-8"))

            cur = payout.get("currentMonth", {})
            prev = payout.get("previousMonth", {})
            cur_payout = (cur.get("payout", 0.0) or 0.0) / 100.0
            cur_held = (cur.get("held", 0.0) or 0.0) / 100.0
            cur_expected = (payout.get("currentMonthExpectations", 0.0) or 0.0) / 100.0
            cur_disk_payout = (cur.get("diskSpacePayout", 0.0) or 0.0) / 100.0
            cur_egress_payout = (cur.get("egressBandwidthPayout", 0.0) or 0.0) / 100.0

            prev_payout = (prev.get("payout", 0.0) or 0.0) / 100.0
            prev_held = (prev.get("held", 0.0) or 0.0) / 100.0

            result["payout"] = {
                "current": {
                    "payout": round(cur_payout, 2),
                    "held": round(cur_held, 2),
                    "earned": round(cur_payout + cur_held, 2),
                    "expected": round(cur_expected, 2),
                    "egressBandwidth": cur.get("egressBandwidth", 0),
                    "egressRepairAudit": cur.get("egressRepairAudit", 0),
                    "diskSpacePayout": round(cur_disk_payout, 2),
                    "egressBandwidthPayout": round(cur_egress_payout, 2)
                },
                "previous": {
                    "payout": round(prev_payout, 2),
                    "held": round(prev_held, 2),
                    "earned": round(prev_payout + prev_held, 2),
                    "egressBandwidth": prev.get("egressBandwidth", 0),
                    "egressRepairAudit": prev.get("egressRepairAudit", 0)
                }
            }
        except Exception as e_payout:
            result["payout_error"] = str(e_payout)

        # 3. Satellites & Audit Scores (/api/sno/satellites/)
        try:
            req_sat = urllib.request.Request(f"{base_url}/api/sno/satellites/", headers={"User-Agent": "StorjMultiDash/1.0"})
            with urllib.request.urlopen(req_sat, timeout=3.5) as resp:
                sat = json.loads(resp.read().decode("utf-8"))

            raw_audits = sat.get("audits", [])
            parsed_audits = []
            for a in raw_audits:
                parsed_audits.append({
                    "satelliteName": a.get("satelliteName", "Unknown"),
                    "auditScore": round(a.get("auditScore", 0.0) * 100.0, 2),
                    "suspensionScore": round(a.get("suspensionScore", 0.0) * 100.0, 2),
                    "onlineScore": round(a.get("onlineScore", 0.0) * 100.0, 2)
                })
            result["audits"] = parsed_audits
        except Exception as e_sat:
            result["sat_error"] = str(e_sat)

    except Exception as e:
        result["online"] = False
        result["error"] = str(e)

    return result


def get_cluster_data(force=False):
    global CACHE_DATA, CACHE_TIMESTAMP
    now = time.time()
    if not force and CACHE_DATA is not None and (now - CACHE_TIMESTAMP) < CACHE_TTL_SECONDS:
        return CACHE_DATA

    config = load_config()
    nodes_cfg = config.get("nodes", [])

    # Poll nodes in parallel
    with ThreadPoolExecutor(max_workers=max(4, len(nodes_cfg))) as executor:
        nodes_data = list(executor.map(fetch_node_stats, nodes_cfg))

    # Compute aggregate summary
    online_count = sum(1 for n in nodes_data if n.get("online"))
    total_nodes = len(nodes_data)

    total_used = sum(n["diskSpace"]["used"] for n in nodes_data if n.get("online"))
    total_allocated = sum(n["diskSpace"]["allocated"] for n in nodes_data if n.get("online"))
    total_available = sum(n["diskSpace"]["available"] for n in nodes_data if n.get("online"))
    total_trash = sum(n["diskSpace"]["trash"] for n in nodes_data if n.get("online"))
    total_reclaimable = sum(n["diskSpace"]["reclaimable"] for n in nodes_data if n.get("online"))
    overall_pct = (total_used / total_allocated * 100.0) if total_allocated > 0 else 0.0

    total_bandwidth_used = sum(n["bandwidth"]["used"] for n in nodes_data if n.get("online"))

    total_current_payout = sum(n["payout"]["current"]["payout"] for n in nodes_data if n.get("online"))
    total_current_held = sum(n["payout"]["current"]["held"] for n in nodes_data if n.get("online"))
    total_current_earned = sum(n["payout"]["current"].get("earned", 0.0) for n in nodes_data if n.get("online"))
    total_current_expected = sum(n["payout"]["current"]["expected"] for n in nodes_data if n.get("online"))

    total_prev_payout = sum(n["payout"]["previous"]["payout"] for n in nodes_data if n.get("online"))
    total_prev_held = sum(n["payout"]["previous"]["held"] for n in nodes_data if n.get("online"))
    total_prev_earned = sum(n["payout"]["previous"].get("earned", 0.0) for n in nodes_data if n.get("online"))

    all_quic_ok = all(n.get("quicStatus") == "OK" for n in nodes_data if n.get("online"))
    versions = list(sorted(set(n.get("version") for n in nodes_data if n.get("online") and n.get("version"))))

    # Compile global satellite scores
    satellites_map = {}
    for n in nodes_data:
        if not n.get("online"):
            continue
        for a in n.get("audits", []):
            s_name = a["satelliteName"].split(":")[0]
            if s_name not in satellites_map:
                satellites_map[s_name] = {
                    "name": s_name,
                    "scores_by_node": {}
                }
            satellites_map[s_name]["scores_by_node"][n["name"]] = {
                "audit": a["auditScore"],
                "suspension": a["suspensionScore"],
                "online": a["onlineScore"]
            }

    CACHE_DATA = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "poll_interval_seconds": config.get("poll_interval_seconds", 30),
        "summary": {
            "onlineNodes": online_count,
            "totalNodes": total_nodes,
            "allHealthy": (online_count == total_nodes and total_nodes > 0),
            "disk": {
                "totalUsed": total_used,
                "totalAllocated": total_allocated,
                "totalAvailable": total_available,
                "totalTrash": total_trash,
                "totalReclaimable": total_reclaimable,
                "percentUsed": round(overall_pct, 1)
            },
            "bandwidth": {
                "totalUsed": total_bandwidth_used
            },
            "payout": {
                "currentEarned": round(total_current_earned, 2),
                "currentPayout": round(total_current_payout, 2),
                "currentHeld": round(total_current_held, 2),
                "currentExpected": round(total_current_expected, 2),
                "previousEarned": round(total_prev_earned, 2),
                "previousPayout": round(total_prev_payout, 2),
                "previousHeld": round(total_prev_held, 2)
            },
            "network": {
                "allQuicOk": all_quic_ok,
                "versions": versions
            }
        },
        "nodes": nodes_data,
        "satellites": list(satellites_map.values())
    }
    CACHE_TIMESTAMP = now
    return CACHE_DATA


class DashboardHandler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        parsed_path = self.path.split("?")[0]
        if parsed_path in ("/api/nodes", "/api/nodes/", "/api/config", "/api/config/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
        elif parsed_path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
        else:
            self.send_error(404, "Not Found")

    def do_GET(self):
        parsed_path = self.path.split("?")[0]

        if parsed_path == "/api/nodes" or parsed_path == "/api/nodes/":
            force = ("force=true" in self.path or "refresh=true" in self.path)
            data = get_cluster_data(force=force)
            self.send_json(data)
            return

        elif parsed_path == "/api/config" or parsed_path == "/api/config/":
            cfg = load_config()
            self.send_json(cfg)
            return

        elif parsed_path == "/health":
            self.send_json({"status": "healthy", "service": "storj-multi-dashboard"})
            return

        elif parsed_path == "/" or parsed_path == "/index.html":
            index_path = os.path.join(STATIC_DIR, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "index.html not found")
            return

        # Serve static assets if any
        if parsed_path.startswith("/static/"):
            rel_path = parsed_path[8:]  # remove /static/
            safe_path = os.path.normpath(os.path.join(STATIC_DIR, rel_path))
            if safe_path.startswith(STATIC_DIR) and os.path.isfile(safe_path):
                ext = os.path.splitext(safe_path)[1].lower()
                mimes = {
                    ".html": "text/html",
                    ".css": "text/css",
                    ".js": "application/javascript",
                    ".json": "application/json",
                    ".svg": "image/svg+xml",
                    ".png": "image/png"
                }
                ctype = mimes.get(ext, "application/octet-stream")
                with open(safe_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed_path = self.path.split("?")[0]
        if parsed_path == "/api/config":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                new_cfg = json.loads(body)
                if "nodes" not in new_cfg or not isinstance(new_cfg["nodes"], list):
                    self.send_json({"error": "Invalid configuration: 'nodes' list required"}, status=400)
                    return
                current = load_config()
                current["nodes"] = new_cfg["nodes"]
                if "poll_interval_seconds" in new_cfg:
                    current["poll_interval_seconds"] = int(new_cfg["poll_interval_seconds"])
                save_config(current)
                # Invalidate cache so next request fetches newly configured nodes immediately
                global CACHE_DATA
                CACHE_DATA = None
                self.send_json({"success": True, "config": current})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        self.send_error(404, "Not Found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress noisy HTTP request logging in terminal, or keep minimal
        sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]} {args[1]}\n")


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


def main():
    config = load_config()
    host = config.get("host", "0.0.0.0")
    port = int(os.environ.get("PORT", config.get("port", 8888)))

    server = HTTPServer((host, port), DashboardHandler)
    local_ip = get_local_ip()

    print("=" * 65)
    print("      STORJ MULTI-NODE SUMMARY DASHBOARD")
    print("=" * 65)
    print(f" * Server listening on: http://{host}:{port}")
    print(f" * Local access:        http://localhost:{port}")
    if local_ip != "127.0.0.1":
        print(f" * LAN access:          http://{local_ip}:{port}")
    print(f" * Monitored Nodes:     {len(config.get('nodes', []))} nodes")
    for n in config.get("nodes", []):
        print(f"    - {n.get('name')} -> {n.get('ip')}:{n.get('port')}")
    print("=" * 65)
    print("Press Ctrl+C to stop.\n")

    pid_file = os.path.join(SCRIPT_DIR, "dashboard.pid")
    try:
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

    def _signal_handler(signum, frame):
        print(f"\n[INFO] Received signal {signum}, gracefully stopping server...")
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down server...")
    finally:
        server.server_close()
        try:
            if os.path.exists(pid_file):
                os.remove(pid_file)
        except Exception:
            pass


if __name__ == "__main__":
    main()
