---
description: How to run the Polymarket crypto monitor (cold start, wipe, restart)
---

# All Commands — Polymarket Monitor

All commands assume you're in PowerShell at the project directory:
```powershell
cd c:\Users\visha\.gemini\antigravity\playground\crystal-perigee
```

---

## 🟢 1. Cold Start (First Run / Fresh Machine)

```powershell
# Install dependencies (one-time)
pip install websocket-client requests streamlit streamlit-autorefresh pandas plotly python-telegram-bot

# Start the monitor (foreground)
$env:PYTHONUNBUFFERED="1"; python crypto_monitor.py

# In a SECOND terminal — start the dashboard
streamlit run dashboard.py --server.port 8501
```

---

## 🔴 2. Full Wipe (Delete All Records + Fresh Start)

```powershell
# Kill everything
taskkill /F /IM python.exe 2>$null

# Delete database + WAL files
Remove-Item -Force trades.db, trades.db-wal, trades.db-shm -ErrorAction SilentlyContinue

# Delete cached market slots (forces fresh fetch)
Remove-Item -Force upcoming_markets.txt -ErrorAction SilentlyContinue

# Restart clean
$env:PYTHONUNBUFFERED="1"; python crypto_monitor.py
```

**One-liner version:**
```powershell
taskkill /F /IM python.exe 2>$null; Start-Sleep 2; Remove-Item -Force trades.db, trades.db-wal, trades.db-shm, upcoming_markets.txt -ErrorAction SilentlyContinue; $env:PYTHONUNBUFFERED="1"; python crypto_monitor.py
```

---

## 🟡 3. Restart After Error (Keep Existing Trades)

```powershell
# Kill the stuck process
taskkill /F /IM python.exe 2>$null

# Restart (keeps trades.db intact, fetches fresh market slots)
$env:PYTHONUNBUFFERED="1"; python crypto_monitor.py
```

> **Note:** The monitor automatically clears `upcoming_markets.txt` on startup and re-fetches. Your existing trades in `trades.db` are preserved.

---

## 🔵 4. Dashboard Only (Monitor Already Running)

```powershell
streamlit run dashboard.py --server.port 8501
```

---

## 🛠️ 5. Useful Debug Commands

```powershell
# Check if python is running
Get-Process python -ErrorAction SilentlyContinue | Format-Table Id, CPU, WorkingSet64

# View last 20 lines of upcoming_markets.txt
Get-Content upcoming_markets.txt -Tail 20

# Check trades in database
python -c "import trade_logger as db; db.init_db(); import sqlite3; conn=sqlite3.connect('trades.db'); [print(r) for r in conn.execute('SELECT id, asset, side_chosen, entry_price, exit_price, outcome FROM trades').fetchall()]"

# Count open vs closed trades
python -c "import sqlite3; c=sqlite3.connect('trades.db'); print('Open:', c.execute('SELECT COUNT(*) FROM trades WHERE exit_price IS NULL').fetchone()[0]); print('Closed:', c.execute('SELECT COUNT(*) FROM trades WHERE exit_price IS NOT NULL').fetchone()[0])"

# Test WebSocket connection independently
python -c "import websocket,json; ws=websocket.create_connection('wss://ws-subscriptions-clob.polymarket.com/ws/market'); print('Connected!'); ws.close()"
```

---

## ⚠️ Key Things to Know

- **Always use `$env:PYTHONUNBUFFERED="1"`** before `python` — otherwise output buffers on Windows and looks frozen
- The monitor **auto-clears** `upcoming_markets.txt` on every restart and fetches fresh slots
- `trades.db` is **never auto-deleted** — only the wipe command removes it
- Dashboard auto-refreshes every 15 seconds
- Fetcher runs every 60 minutes in the background
