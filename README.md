# Storj Multi-Node Summary Dashboard

A lightweight, zero-dependency Python dashboard and Docker container that unifies and displays live statistics across multiple Storj storage nodes on your local network.

---

## Features

- **Cluster Aggregate Performance**:
  - Combined storage capacity, used space, trash, free space, and fill percentage.
  - Total month-to-date earnings, held amount, and projected month-end payout.
  - Previous month earnings comparison.
  - Aggregated bandwidth transferred (egress + audit + repair).
  - Overall cluster health, QUIC status, and running Storj node versions.
- **Individual Node Cards**:
  - Live online/offline status, node ID (with one-click copy), version, and uptime.
  - Direct deep-link buttons (`Dashboard ↗`) to open the native node portal (`http://<node-ip>:20909`).
  - Storage breakdown: used, available, trash, reclaimable, and color-coded utilization gauge (green &rarr; amber &rarr; red).
  - Payout breakdown: current earned, projected, previous month, and disk/bandwidth payout shares.
- **Satellite Scores Matrix**:
  - Compares Audit Score, Suspension Score, and Online Score for each satellite across all nodes in a side-by-side table.
- **Auto-Refresh & In-App Node Management**:
  - Live configurable auto-refresh countdown (10s, 30s, 1m, 5m, or Paused).
  - Instant manual refresh button.
  - Interactive "Nodes" management modal to add/edit/remove node IPs and ports without stopping the server.
- **Zero External Dependencies**:
  - Built strictly using the Python 3 standard library (`http.server`, `urllib.request`, `concurrent.futures`).
  - Offline-ready single page UI with embedded SVG icons and dark-mode styling (no external CDN required).
  - Tiny Docker container (~55 MB total) based on Alpine Linux.

---

## Quick Start (Docker / TrueNAS SCALE)

### 1. TrueNAS SCALE (Electric Eel / Fangtooth)

1. Open your TrueNAS Web UI and navigate to **Apps** &rarr; **Discover Apps** &rarr; **Install Custom App**.
2. Set the Application Name to `storj-dashboard`.
3. Provide the Compose configuration from `docker-compose.yml`:
   ```yaml
   services:
     storj-dashboard:
       image: ghcr.io/<your-username>/storj_multi_dashboard:latest
       container_name: storj-multi-dashboard
       restart: unless-stopped
       ports:
         - "8888:8888"
       environment:
         - PORT=8888
         - CONFIG_PATH=/config/config.json
       volumes:
         - /mnt/<your-pool>/appdata/storj-dashboard:/config

   x-portals:
     - name: "Web UI"
       scheme: "http"
       host: "0.0.0.0"
       port: 8888
       path: "/"
   ```
4. Click **Install**. Once running, click the **Web UI** portal button on the application card.
5. In the web dashboard, click **Nodes** in the header to add your Storj storage node IPs and ports.

### 2. Standalone Docker

```bash
docker run -d \
  --name storj-multi-dashboard \
  -p 8888:8888 \
  -v $(pwd)/config:/config \
  ghcr.io/<your-username>/storj_multi_dashboard:latest
```

---

## Running from Source (Local / Bare Metal)

### 1. Start the Dashboard
```bash
./start.sh
```
Or run directly in foreground:
```bash
./start.sh --foreground
```

### 2. Access the Dashboard
- **Local machine**: `http://localhost:8888`
- **From LAN**: `http://<lan-ip>:8888`

### 3. Check Status & Stop
```bash
./status.sh
./stop.sh
```

---

## Optional: Run as a Systemd Service

```bash
sudo cp storj-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now storj-dashboard.service
```

---

## Configuration (`config.json`)

Nodes can be added and managed directly from the web UI by clicking the **Nodes** button, or configured manually in `config.json`:

```json
{
  "host": "0.0.0.0",
  "port": 8888,
  "poll_interval_seconds": 30,
  "nodes": [
    {
      "id": "node-1",
      "name": "Storage Node 1",
      "ip": "192.168.1.100",
      "port": 20909
    }
  ]
}
```

---

## API Endpoints

- `GET /` &bull; Single-page dashboard interface
- `GET /api/nodes` &bull; Aggregated cluster stats and per-node data (cached for 5s)
- `GET /api/nodes?force=true` &bull; Force immediate parallel query across all nodes
- `GET /api/config` &bull; Read current configuration
- `POST /api/config` &bull; Update nodes list and poll interval
- `GET /health` &bull; Health probe (`{"status": "healthy"}`)
