import csv
import html
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
os.makedirs("docs", exist_ok=True)


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
data = {}

for name, (key, secret) in BOTS.items():
    h = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    trades = closed_trades(h)
    write_csv(f"reports/{name}_trades.csv", trades, FIELDS)
    positions = get(h, "/positions")
    equity[name] = float(get(h, "/account")["equity"])
    realized = sum(t["pnl_usd"] for t in trades)
    wins = sum(1 for t in trades if t["pnl_usd"] > 0)
    unreal = sum(float(p["unrealized_pl"]) for p in positions)
    data[name] = {"equity": equity[name], "realized": realized,
                  "wins": wins, "unreal": unreal,
                  "trades": trades, "positions": positions}
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


# ---------- dashboard page ----------
CSS = (
    ":root{--bg:#fff;--fg:#111;--card:#f3f4f6;--muted:#6b7280;"
    "--pos:#16a34a;--neg:#dc2626;color-scheme:light dark}"
    "@media(prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;"
    "--card:#161b22;--muted:#8b949e;--pos:#3fb950;--neg:#f85149}}"
    "body{margin:0 auto;max-width:640px;padding:16px;"
    "padding-top:max(16px,env(safe-area-inset-top));background:var(--bg);"
    "color:var(--fg);font:15px/1.4 -apple-system,system-ui,sans-serif}"
    "h1{font-size:24px;margin:8px 0 0}h2{font-size:19px;margin:28px 0 8px}"
    "h3{font-size:14px;margin:18px 0 6px;color:var(--muted)}"
    ".muted{color:var(--muted)}.pos{color:var(--pos)}.neg{color:var(--neg)}"
    ".cards{display:grid;grid-template-columns:1fr 1fr;gap:8px}"
    ".card{background:var(--card);border-radius:12px;padding:10px 12px}"
    ".card b{display:block;font-size:12px;font-weight:500;"
    "color:var(--muted)}.card span{font-size:17px;font-weight:600}"
    ".scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}"
    "th,td{text-align:right;padding:6px 4px;white-space:nowrap}"
    "th:first-child,td:first-child{text-align:left}"
    "th{font-size:12px;color:var(--muted);font-weight:500}"
    "tr+tr td{border-top:1px solid var(--card)}"
    ".chart{width:100%;height:auto;background:var(--card);border-radius:12px}"
)


def money(x):
    return f"{'-' if x < 0 else ''}${abs(x):,.2f}"


def sign(x):
    return "pos" if x > 0 else "neg" if x < 0 else ""


def card(label, value, css=""):
    return f"<div class='card'><b>{label}</b><span class='{css}'>{value}</span></div>"


def chart(ordered):
    pts = [(float(r["bot1_equity"]), float(r["bot2_equity"])) for r in ordered]
    if len(pts) < 2:
        return "<p class='muted'>The chart appears once there are two days of data.</p>"
    lo = min(min(p) for p in pts)
    hi = max(max(p) for p in pts)
    if hi == lo:
        hi = lo + 1
    w, ht, pad = 340, 160, 14

    def line(idx):
        out = []
        for i, p in enumerate(pts):
            x = pad + i * (w - 2 * pad) / (len(pts) - 1)
            y = ht - pad - (p[idx] - lo) * (ht - 2 * pad) / (hi - lo)
            out.append(f"{x:.1f},{y:.1f}")
        return " ".join(out)

    return (
        f"<svg viewBox='0 0 {w} {ht}' class='chart'>"
        f"<polyline points='{line(0)}' fill='none' stroke='#2f80ed' stroke-width='2.5'/>"
        f"<polyline points='{line(1)}' fill='none' stroke='#f2994a' stroke-width='2.5'/>"
        "</svg><p class='muted'>"
        "<span style='color:#2f80ed'>&#9632;</span> Bot 1 &nbsp; "
        "<span style='color:#f2994a'>&#9632;</span> Bot 2 &nbsp; "
        f"{money(lo)} to {money(hi)}</p>"
    )


def bot_section(label, d):
    t = d["trades"]
    n = len(t)
    win = f"{d['wins'] / n:.0%} of {n}" if n else "no trades yet"
    out = [
        f"<h2>{label}</h2><div class='cards'>",
        card("Equity", money(d["equity"])),
        card("Win rate", win),
        card("Realized P/L", money(d["realized"]), sign(d["realized"])),
        card("Open P/L", money(d["unreal"]), sign(d["unreal"])),
        "</div><h3>OPEN POSITIONS</h3>",
    ]
    if d["positions"]:
        out.append("<div class='scroll'><table><tr><th>Stock</th><th>Entry</th>"
                   "<th>Now</th><th>P/L</th></tr>")
        for p in d["positions"]:
            pl = float(p["unrealized_plpc"])
            out.append(
                f"<tr><td>{html.escape(p['symbol'])}</td>"
                f"<td>{float(p['avg_entry_price']):.2f}</td>"
                f"<td>{float(p['current_price']):.2f}</td>"
                f"<td class='{sign(pl)}'>{pl:.2%}</td></tr>")
        out.append("</table></div>")
    else:
        out.append("<p class='muted'>None</p>")
    out.append("<h3>RECENT CLOSED TRADES</h3>")
    if t:
        out.append("<div class='scroll'><table><tr><th>Stock</th><th>Buy</th>"
                   "<th>Sell</th><th>P/L</th><th>%</th><th>Days</th></tr>")
        for x in reversed(t[-15:]):
            out.append(
                f"<tr><td>{html.escape(x['symbol'])}</td>"
                f"<td>{x['buy_price']:.2f}</td><td>{x['sell_price']:.2f}</td>"
                f"<td class='{sign(x['pnl_usd'])}'>{money(x['pnl_usd'])}</td>"
                f"<td class='{sign(x['pnl_pct'])}'>{x['pnl_pct']:.2f}%</td>"
                f"<td>{x['days_held']}</td></tr>")
        out.append("</table></div>")
    else:
        out.append("<p class='muted'>None yet</p>")
    return "".join(out)


ordered = [rows[k] for k in sorted(rows)]
page = (
    "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    "<meta name='robots' content='noindex'>"
    "<meta name='apple-mobile-web-app-capable' content='yes'>"
    "<meta name='apple-mobile-web-app-title' content='Bots'>"
    f"<title>Bot dashboard</title><style>{CSS}</style></head><body>"
    "<h1>Bot dashboard</h1>"
    f"<p class='muted'>Updated {now:%Y-%m-%d %H:%M} UTC</p>"
    "<h2>Equity</h2>" + chart(ordered)
    + bot_section("Bot 1 (top gainer)", data["bot1"])
    + bot_section("Bot 2 (most active)", data["bot2"])
    + "</body></html>"
)
with open("docs/index.html", "w") as f:
    f.write(page)
print("Report and dashboard written")
