"""List of tracked orders.

Copy this file to orders.py (git-ignored, since it will contain your
personal tracking numbers/order IDs) and fill in your own orders there.
This is the only place you need to edit by hand when a new order shows
up — add an item to the list. The script itself (check_orders.py) never
writes to this file and doesn't store the order list on its own — only
the last known status of each order (in SQLite), to know whether it
changed since the previous run.

Two kinds of entries:

1. A parcel by tracking number (checked via 17TRACK, works with almost
   any site/carrier):
   {
       "label": "Headphones",               # how it's labeled in messages
       "kind": "parcel",
       "tracking_number": "RR123456789CN",
       "carrier_code": None,                 # optional, 17TRACK usually detects it
   }

2. An order on a store's website via an adapter (see providers/registry.py
   — you need to wire up a provider for the specific site there first):
   {
       "label": "Sneakers",
       "kind": "store",
       "site": "generic",                   # provider key in providers/registry.py
       "order_id": "12345-6789",
   }

   The "cypost" provider (Cyprus Post, providers/cypost.py) uses the same
   shape, but "order_id" holds the shipment number rather than an order
   ID — it's wired up with no extra setup, no key/login needed:
   {
       "label": "Headphones (Cyprus Post)",
       "kind": "store",
       "site": "cypost",
       "order_id": "LW541531090DE",
   }

   The "imusic" provider (providers/imusic.py) — iMusic order status via
   the public ticket link of the form https://imusic.co/ticket/<id>; pass
   the <id> from that link as "order_id". Note: the site detects headless
   browsers, so this adapter launches Chromium NOT headless — see details
   and how to run it on a schedule (Task Scheduler / xvfb-run in CI) in
   the providers/imusic.py docstring.
   {
       "label": "Vinyl records (iMusic)",
       "kind": "store",
       "site": "imusic",
       "order_id": "90KOG9m78dThhLyNTAPsrDkoyGN2XeCgyPuVxiPVgOU",
   }

The optional "key" field is a stable identifier for the status history in
the DB. If omitted, it's derived automatically from kind + number/site.
Set "key" by hand if you plan to change the tracking_number/order_id of an
existing entry but want to keep its status history.
"""

ORDERS = [
    # {
    #     "label": "Headphones",
    #     "kind": "parcel",
    #     "tracking_number": "RR123456789CN",
    #     "carrier_code": None,
    # },
    # {
    #     "label": "Headphones (Cyprus Post)",
    #     "kind": "store",
    #     "site": "cypost",
    #     "order_id": "LW541531090DE",
    # },
    # {
    #     "label": "Vinyl records (iMusic)",
    #     "kind": "store",
    #     "site": "imusic",
    #     "order_id": "<id from your imusic.co/ticket/<id> link>",
    # },
    # {
    #     "label": "Sneakers",
    #     "kind": "store",
    #     "site": "generic",
    #     "order_id": "12345-6789",
    # },
]
