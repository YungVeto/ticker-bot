import csv
import os
from datetime import datetime, timezone

import requests

BASE = "https://paper-api.alpaca.markets/v2"
BOTS = {
    "bot1": (os.environ["ALPACA_KEY"], os.environ["ALPACA_SECRET"]),
    "bot2": (os.environ["ALPACA_KEY_2"], os.environ["ALPACA_SECRET_2"]),
}
FIELDS = ["symbol", "buy_time", "buy_price", "sell_time", "sell_price",
          "qty", "pnl_usd", "pnl_pct", "days_held"]
os.makedirs("reports", exist_ok=True)


def get(h, path, **params):
    r = requests.get(BASE + path, headers=h, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def ts(s):
    return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def closed_trades(h):
    orders = get(h, "/orders", status="closed", limit=500, direction="asc")
    lots, trades = {}, []
    for o in orders:
        qty = float(o["filled_qty"] or 0)
        if qty <= 0 or not o["filled_at"]:
            continue
        sym = o["symbol"]
        price = float(o["filled_avg_price"])
        when = ts(o["filled_at"])
        if o["side"] == "buy":
            lots.setdefault(sym, []).append([qty, price, when])
            continue
        left = qty
        while left > 1e-9 and lots.get(sym):
            lot = lots[sym][0]
            take = min(left, lot[0])
            trades.append({
                "symbol": sym,
                "buy_time": lot[2].isoformat(" "),
                "buy_price": round(lot[1], 2),
                "sell_time": when.isoformat(" "),
                "sell_price": round(price, 2),
                "qty": round(take, 4),
                "pnl_usd": round((price - lot[1]) * take, 2),
                "pnl_pct": round((price / lot[1] - 1) * 100, 2),
                "days_held": (when - lot[2]).days,
            })
            lot[0] -= take
            left -= take
            if lot[0] <= 1e-9:
                lots[sym].pop(0)
    return trades


now = datetime.now(timezone.utc)
summary = ["# Bot report", f"Updated {now:%Y-%m-%d %H:%M} UTC", ""]
equity = {}

for name, (key, secret) in BOTS.items():
    h = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    trades = closed_trades(h)
    write_csv(f"reports/{name}_trades.csv", trades, FIELDS)
    positions = get(h, "/positions")
    equity[name] = float(get(h, "/account")["equity"])
    realized = sum(t["pnl_usd"] for t in trades)
    wins = sum(1 for t in trades if t["pnl_usd"] > 0)
    unreal = sum(float(p["unrealized_pl"]) for p in positions)
    summary += [
        f"## {name}",
        f"- Equity: ${equity[name]:,.2f}",
        f"- Closed trades: {len(trades)} ({wins} winners)",
        f"- Realized P/L: ${realized:,.2f}",
        f"- Open positions: {len(positions)} "
        f"(unrealized P/L ${unreal:,.2f})",
    ]
    for p in positions:
        summary.append(
            f"  - {p['symbol']}: bought at {float(p['avg_entry_price']):.2f}, "
            f"now {float(p['current_price']):.2f}, "
            f"{float(p['unrealized_plpc']):.2%}")
    summary.append("")

with open("reports/summary.md", "w") as f:
    f.write("\n".join(summary))

path = "reports/equity.csv"
rows = {}
if os.path.exists(path):
    with open(path) as f:
        rows = {r["date"]: r for r in csv.DictReader(f)}
today = now.strftime("%Y-%m-%d")
rows[today] = {"date": today, "bot1_equity": equity["bot1"],
               "bot2_equity": equity["bot2"]}
write_csv(path, list(rows.values()), ["date", "bot1_equity", "bot2_equity"])
print("Report written")
