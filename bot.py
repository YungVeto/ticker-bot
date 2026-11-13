import os
from datetime import datetime, timezone
import requests

TRADE = "https://paper-api.alpaca.markets/v2"
DATA = "https://data.alpaca.markets"
H = {
    "APCA-API-KEY-ID": os.environ["ALPACA_KEY"],
    "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET"],
}
NOTIONAL = "1000"    # dollars per paper trade
MIN_PRICE = 10.0     # skip cheap, spiky stocks
TAKE_PROFIT = 0.01   # sell at +1%
STOP_LOSS = -0.02    # sell at -2%
MAX_DAYS = 3         # sell after 3 days


def get(url, **params):
    r = requests.get(url, headers=H, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def days_held(sym):
    orders = get(f"{TRADE}/orders", status="closed", symbols=sym,
                 direction="desc", limit=50)
    for o in orders:
        if o["side"] == "buy" and o["filled_at"]:
            t = datetime.strptime(o["filled_at"][:19], "%Y-%m-%dT%H:%M:%S")
            t = t.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - t).days
    return 0


def check_sells():
    for p in get(f"{TRADE}/positions"):
        sym = p["symbol"]
        pl = float(p["unrealized_plpc"])
        days = days_held(sym)
        print(f"{sym}: P/L {pl:.2%}, held {days} days")
        reason = None
        if pl >= TAKE_PROFIT:
            reason = "take profit"
        elif pl <= STOP_LOSS:
            reason = "stop loss"
        elif days >= MAX_DAYS:
            reason = "time limit"
        if reason:
            r = requests.delete(f"{TRADE}/positions/{sym}",
                                headers=H, timeout=30)
            print(f"Selling {sym} ({reason}):", r.status_code, r.text[:200])


def bought_today():
    midnight = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    orders = get(f"{TRADE}/orders", status="all", after=midnight, limit=50)
    return any(o["side"] == "buy" for o in orders)


def pick_ticker(held):
    data = get(f"{DATA}/v1beta1/screener/stocks/movers", top=20)
    for item in data["gainers"]:
        sym = item["symbol"]
        if sym in held or not sym.isalpha() or len(sym) > 5:
            continue
        if item["price"] >= MIN_PRICE:
            print(f"Top gainer: {sym} up {item['percent_change']}%")
            return sym, item["price"]
    return None, None


check_sells()

if bought_today():
    print("Already bought today, skipping buy")
    raise SystemExit

held = {p["symbol"] for p in get(f"{TRADE}/positions")}
sym, price = pick_ticker(held)
if not sym:
    print("No suitable ticker found")
    raise SystemExit

print(f"Buying ${NOTIONAL} of {sym} at about {price}")
order = requests.post(
    f"{TRADE}/orders", headers=H, timeout=30,
    json={"symbol": sym, "notional": NOTIONAL, "side": "buy",
          "type": "market", "time_in_force": "day"},
)
print(order.status_code, order.json())
