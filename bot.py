import os
import requests

BASE = "https://paper-api.alpaca.markets/v2"
HEADERS = {
    "APCA-API-KEY-ID": os.environ["ALPACA_KEY"],
    "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET"],
}

# Check the connection
acct = requests.get(f"{BASE}/account", headers=HEADERS, timeout=30)
acct.raise_for_status()
print("Account status:", acct.json()["status"])

# Place a test paper order: buy 1 share of AAPL
order = requests.post(
    f"{BASE}/orders",
    headers=HEADERS,
    timeout=30,
    json={
        "symbol": "AAPL",
        "qty": "1",
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
    },
)
print(order.status_code, order.json())
