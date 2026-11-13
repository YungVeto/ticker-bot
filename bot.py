import os
import requests

TRADE = "https://paper-api.alpaca.markets/v2"
DATA = "https://data.alpaca.markets"
H = {
    "APCA-API-KEY-ID": os.environ["ALPACA_KEY"],
    "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET"],
}
NOTIONAL = "100"   # dollars per paper trade
MIN_PRICE = 5.0    # skip penny stocks


def get(url, **params):
    r = requests.get(url, headers=H, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def pick_ticker():
    data = get(f"{DATA}/v1beta1/screener/stocks/most-actives",
               by="volume", top=20)
    for item in data["most_actives"]:
        sym = item["symbol"]
        if not sym.isalpha() or len(sym) > 5:
            continue
        price = get(f"{DATA}/v2/stocks/{sym}/trades/latest",
                    feed="iex")["trade"]["p"]
        if price >= MIN_PRICE:
            return sym, price
    return None, None


sym, price = pick_ticker()
if not sym:
    print("No suitable ticker found")
    raise SystemExit

held = {p["symbol"] for p in get(f"{TRADE}/positions")}
if sym in held:
    print(f"Already holding {sym}, skipping")
    raise SystemExit

print(f"Buying ${NOTIONAL} of {sym} at about {price}")
order = requests.post(
    f"{TRADE}/orders", headers=H, timeout=30,
    json={"symbol": sym, "notional": NOTIONAL, "side": "buy",
          "type": "market", "time_in_force": "day"},
)
print(order.status_code, order.json())
