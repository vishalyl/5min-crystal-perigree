"""
market_fetcher.py — Auto-discover upcoming Polymarket 15m crypto markets
=========================================================================
Generates upcoming 15-minute slot timestamps, constructs the slug for each
crypto, fetches clobTokenIds from the Gamma API, and appends new slots to
upcoming_markets.txt.

Can run standalone:  python market_fetcher.py
Also called from crypto_monitor.py every 15 minutes as a background task.
"""

import datetime
import json
import re
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from zoneinfo import ZoneInfo

ET_TZ = ZoneInfo("America/New_York")
GAMMA_API_BASE = "https://gamma-api.polymarket.com/markets/slug/"
MARKETS_FILE = Path(__file__).parent / "upcoming_markets.txt"
INTERVAL = 900       # 15 minutes in seconds
FETCH_INTERVAL = 900  # Re-fetch every 15 minutes
COUNT = 10            # Number of future intervals to generate

CRYPTOS = ["btc", "eth", "sol", "xrp"]

# Colors
CYAN   = "\033[96m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
MAGENTA= "\033[95m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def get_existing_slot_labels():
    """Read upcoming_markets.txt and return a set of slot labels already present."""
    if not MARKETS_FILE.exists():
        return set()
    text = MARKETS_FILE.read_text(encoding="utf-8")
    return set(re.findall(r"🕒\s*Slot:\s*(.+)", text))


def _fetch_single_market(slug, crypto_label):
    """Fetch a single market's token IDs from Gamma API."""
    url = f"https://polymarket.com/event/{slug}"
    try:
        resp = requests.get(f"{GAMMA_API_BASE}{slug}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            tokens = json.loads(data.get("clobTokenIds", "[]"))
            return crypto_label, url, tokens[0] if len(tokens) > 0 else "N/A", tokens[1] if len(tokens) > 1 else "N/A"
    except Exception:
        pass
    return crypto_label, url, "Error", "Error"


def fetch_upcoming_slots():
    """
    Fetch the next COUNT 15-minute market slots from the Gamma API.
    Uses Unix timestamp alignment: round down to last 15-min boundary,
    then generate COUNT future intervals.
    """
    now = int(time.time())
    last_interval = now - (now % INTERVAL)

    # Build all tasks: (slot_index, crypto, slug, timestamp)
    tasks = []
    slot_meta = []  # (display_time, unix_timestamp) per slot
    for i in range(1, COUNT + 1):
        next_timestamp = last_interval + (i * INTERVAL)
        date_obj = datetime.datetime.fromtimestamp(next_timestamp, tz=ET_TZ)
        display_time = date_obj.strftime("%Y-%m-%d %I:%M %p EST")
        slot_meta.append({"label": display_time, "timestamp": next_timestamp})

        for coin in CRYPTOS:
            slug = f"{coin}-updown-15m-{next_timestamp}"
            tasks.append((i - 1, coin.upper(), slug))

    # Fire all requests concurrently (COUNT * 4 cryptos)
    results = {}  # (slot_idx, crypto) -> {url, yes, no}
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {
            pool.submit(_fetch_single_market, slug, crypto_label): (idx, crypto_label)
            for idx, crypto_label, slug in tasks
        }
        for future in as_completed(futures):
            idx, crypto_label = futures[future]
            label, url, yes_tok, no_tok = future.result()
            results[(idx, crypto_label)] = {"url": url, "yes": yes_tok, "no": no_tok}

    # Assemble into slot list
    slots = []
    for i in range(COUNT):
        slot = {"label": slot_meta[i]["label"], "markets": {}}
        for coin in CRYPTOS:
            crypto_label = coin.upper()
            slot["markets"][crypto_label] = results.get(
                (i, crypto_label), {"url": "", "yes": "Error", "no": "Error"}
            )
        slots.append(slot)

    return slots


def format_slot_block(slot):
    """Format a slot dict into the upcoming_markets.txt block format."""
    lines = [f"🕒 Slot: {slot['label']}"]
    for crypto in ["BTC", "ETH", "SOL", "XRP"]:
        if crypto in slot["markets"]:
            m = slot["markets"][crypto]
            lines.append(f"   {crypto}: {m['url']}")
            lines.append(f"        ✅ YES: {m['yes']}")
            lines.append(f"        ❌ NO : {m['no']}")
    return "\n".join(lines)


def append_new_slots(new_slots):
    """Append new slot blocks to upcoming_markets.txt."""
    if not new_slots:
        return 0

    existing = ""
    if MARKETS_FILE.exists():
        existing = MARKETS_FILE.read_text(encoding="utf-8").rstrip()
        if existing.endswith("-" * 70):
            existing = existing[:-70].rstrip()

    blocks = [format_slot_block(s) for s in new_slots]
    new_content = existing + "\n\n" + "\n\n".join(blocks) + "\n\n" + "-" * 70 + "\n"
    MARKETS_FILE.write_text(new_content, encoding="utf-8")
    return len(new_slots)


def discover_and_append():
    """Main discovery: fetch slots, deduplicate, append new ones."""
    now_str = datetime.datetime.now(ET_TZ).strftime("%I:%M %p EST")
    print(f"\n{MAGENTA}[FETCHER]{RESET} {now_str} — Checking for new 15m market slots...")

    existing_labels = get_existing_slot_labels()
    print(f"  {DIM}Existing slots in file: {len(existing_labels)}{RESET}")

    fetched_slots = fetch_upcoming_slots()
    print(f"  {DIM}Fetched from API: {len(fetched_slots)} slots{RESET}")

    new_slots = []
    for slot in fetched_slots:
        if slot["label"] not in existing_labels:
            valid_tokens = sum(
                1 for m in slot["markets"].values()
                if m["yes"] not in ("Not indexed", "Error", "N/A")
            )
            if valid_tokens >= 3:
                new_slots.append(slot)
                print(f"  {GREEN}+ NEW:{RESET} {slot['label']} ({valid_tokens}/4 valid)")
            else:
                print(f"  {YELLOW}~ SKIP:{RESET} {slot['label']} (only {valid_tokens}/4 indexed)")
        else:
            print(f"  {DIM}  EXISTS: {slot['label']}{RESET}")

    if new_slots:
        count = append_new_slots(new_slots)
        print(f"  {GREEN}✓ Appended {count} new slot(s) to {MARKETS_FILE.name}{RESET}")
    else:
        print(f"  {DIM}No new slots to add.{RESET}")

    return new_slots


def fetcher_loop():
    """Background loop: run discovery every FETCH_INTERVAL seconds."""
    while True:
        time.sleep(FETCH_INTERVAL)
        try:
            discover_and_append()
        except Exception as e:
            print(f"{RED}[FETCHER ERR]{RESET} {e}")


def start_fetcher():
    """Start the market fetcher as a background daemon thread."""
    t = threading.Thread(target=fetcher_loop, daemon=True)
    t.start()
    print(f"  {MAGENTA}✓ Market fetcher started (every {FETCH_INTERVAL // 60} min){RESET}")


# ─── Standalone mode ─────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{BOLD}Polymarket 15m Market Discovery{RESET}")
    print(f"  File: {MARKETS_FILE}")
    slots = discover_and_append()
    print(f"\n{GREEN}Done.{RESET}")
