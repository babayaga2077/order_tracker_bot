# Telegram order-tracking bot

Not an always-running service, but a one-shot script `check_orders.py` that
you run on a schedule (cron / Task Scheduler / CI). It doesn't accept
commands in Telegram — it only sends a notification when an order's status
changes. You edit the order list by hand in `orders.py` and commit it to
the repo; the script itself stores only the last known status of each
order (in SQLite), to know what changed.

Two ways to track:

1. **A parcel by tracking number** — via [17TRACK](https://www.17track.net/en/api),
   3000+ carriers with carrier auto-detection. Covers deliveries from
   almost any site (Ozon, Wildberries, AliExpress, overseas stores, etc.)
   as long as you have a tracking number.
2. **An order status shown directly on a store's site** — via an adapter
   (`providers/store_generic.py`). Marketplaces don't have an open
   order-status API, so the adapter emulates a logged-in user via
   Playwright and needs manual setup per site (see below). A more fragile
   approach — site markup and anti-bot protection change without notice.

Ready-made built-in adapter: **Cyprus Post** (`providers/cypost.py`, key
`site: "cypost"`) — reads the official tracker at
`ips.cypruspost.gov.cy/ipswebtrack`, no key/login needed, always wired up.
Useful as a fallback source when 17TRACK hasn't picked up the status yet
for a shipment that already arrived in Cyprus (put the shipment number in
the `order_id` field, example in `orders.py`).

Also built in: **iMusic** (`providers/imusic.py`, key `site: "imusic"`) —
reads the order status from a public `imusic.co/ticket/<id>` link via
Playwright. No key/login needed either, but the site detects headless
browsers, so this adapter launches a non-headless Chromium — see
`providers/imusic.py` for how to run that unattended (Task Scheduler /
`xvfb-run` in CI).

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
cp orders.example.py orders.py
```

`orders.py` holds your personal tracking numbers/order IDs, so it's
git-ignored — you edit your own local copy and it never gets committed.

Fill in `.env`:

- `TELEGRAM_BOT_TOKEN` — get one from [@BotFather](https://t.me/BotFather)
  (the `/newbot` command).
- `TELEGRAM_CHAT_ID` — where notifications are sent. Send your bot any
  message once, then open in a browser
  `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates` and find
  `"chat": {"id": ...}`. Easier: send `/start` to `@userinfobot` — it
  immediately shows your id (same id, if sent from the same account).
- `TRACK17_API_KEY` — sign up at https://www.17track.net/en/api
  (free, 100 tracking numbers/month on trial), key under
  Settings → Security → Access Key.

## How to use it

1. Open `orders.py`, add an order to the list (examples in the comments at
   the top of the file and in `orders.example.py`). No need to commit —
   `orders.py` is git-ignored.
2. The scheduled script picks up the new order automatically on its next run.
3. Remove an order from the list — its status is also removed from the
   local DB on the next run.

Manual run (to check everything is set up correctly):

```bash
python check_orders.py
```

If something's off (token/key missing, site not configured) — the script
logs it and doesn't crash entirely: the other orders are still checked.

## Running on a schedule

The script doesn't "hang around" by itself — an OS/CI scheduler drives it.

### cron (Linux/macOS)

```bash
crontab -e
```

```
*/30 * * * * cd /path/to/order_tracker_bot && /path/to/venv/bin/python check_orders.py >> cron.log 2>&1
```

### Windows Task Scheduler

Create a task: trigger — "Repeat every 30 minutes", action — run the
program `venv\Scripts\python.exe` with argument `check_orders.py` and
working directory set to the project folder.

### GitHub Actions (if the code already lives in a repo)

```yaml
# .github/workflows/check_orders.yml
on:
  schedule:
    - cron: "*/30 * * * *"
  workflow_dispatch:
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: playwright install --with-deps chromium
      - run: sudo apt-get update && sudo apt-get install -y xvfb
      - run: xvfb-run -a python check_orders.py
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          TRACK17_API_KEY: ${{ secrets.TRACK17_API_KEY }}
```

`xvfb-run` gives Chromium a virtual display: the browser launches non-
headless (needed to get past the anti-bot in `providers/imusic.py` — see
its docstring), but the runner stays fully non-interactive. If none of
your providers need Playwright, you can drop the `playwright install` and
`xvfb-run` steps and just call `python check_orders.py` directly.

Important caveat: GitHub Actions runners are ephemeral, so the
`orders.db` file (SQLite with statuses) won't persist between runs on its
own — you need to either cache it via `actions/cache` (keyed on something
stable, e.g. the repo name) or commit `orders.db` back to the repo as a
separate step. Without that, the bot will treat every check as the
"first" one and never send a change notification. For simplicity, cron on
your own server/computer is usually more convenient.

Another caveat: `orders.py` is git-ignored (see below), so a plain
checkout won't have it on the runner. Either store its content in a
`ORDERS_PY` repo secret and write it out as a step before running:

```yaml
      - run: echo "$ORDERS_PY" > orders.py
        env:
          ORDERS_PY: ${{ secrets.ORDERS_PY }}
```

or, if you don't mind your tracking numbers/order IDs being in the repo,
just remove `orders.py` from `.gitignore` and commit it normally.

### GitLab CI/CD

GitLab's equivalent of GitHub Actions is called **GitLab CI/CD**: the
pipeline is defined in `.gitlab-ci.yml` (already included in this repo),
and the schedule itself is configured separately in the UI rather than
inside the file.

```yaml
# .gitlab-ci.yml
check_orders:
  image: python:3.11
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
    - if: $CI_PIPELINE_SOURCE == "web"
  cache:
    key: orders-db
    paths:
      - orders.db
  before_script:
    - apt-get update && apt-get install -y xvfb
    - pip install -r requirements.txt
    - playwright install --with-deps chromium
    - echo "$ORDERS_PY" > orders.py
  script:
    - xvfb-run -a python check_orders.py
```

Setup steps:

1. Push this repo to GitLab (`git push` to your project).
2. **Settings → CI/CD → Variables** — add `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`, `TRACK17_API_KEY`, and `ORDERS_PY` (the full
   contents of your local `orders.py`, since it's git-ignored and
   otherwise won't exist on the runner). Mark them "Protected" and
   "Masked" as appropriate — GitLab CI/CD variables are injected as
   environment variables automatically, so `config.py`'s `os.getenv(...)`
   picks them up with no extra wiring.
3. **Build → Pipeline schedules → New schedule** — set the interval
   (e.g. `*/30 * * * *`) and the target branch. This replaces the
   `on: schedule:` block from the GitHub Actions example — GitLab doesn't
   support cron directly in `.gitlab-ci.yml`.
4. The `rules:` block above makes the job run for scheduled pipelines and
   for manual "Run pipeline" clicks in the UI, but not on every push.

The same caveats as GitHub Actions apply here: runners are ephemeral, so
`orders.db` needs the `cache:` block to persist between runs (best-effort,
not guaranteed — GitLab may still evict it), and `orders.py` has to be
reconstructed from the `ORDERS_PY` variable on each run.

## How to add your own site (Ozon, Wildberries, AliExpress...)

1. `pip install playwright && playwright install chromium`
2. Log in manually in a browser once and save cookies:

   ```python
   from playwright.sync_api import sync_playwright
   with sync_playwright() as p:
       browser = p.chromium.launch(headless=False)
       page = browser.new_page()
       page.goto("https://example.com/login")
       input("Log in, then press Enter...")
       page.context.storage_state(path="site_state.json")
   ```

3. Copy `providers/store_generic.py` into a separate file (e.g.
   `providers/ozon.py`) and plug in the real order-page URL and the CSS
   selector for the status block (check the browser's DevTools).
4. Wire up the new adapter in `providers/registry.py`:

   ```python
   from .ozon import OzonProvider
   store_providers["ozon"] = OzonProvider("site_state.json")
   ```

5. Add an entry with `"site": "ozon"` to `orders.py`.

Keep in mind that automated access to a personal account may violate a
given site's terms of service — use at your own risk and only for your
own orders.

## Project structure

```
order_tracker_bot/
├── orders.py              # your order list — git-ignored, edit this by hand
├── orders.example.py      # template for orders.py, safe to commit
├── check_orders.py        # one-shot check script, entry point
├── config.py              # reads .env
├── db.py                  # SQLite: last status of each order
├── providers/
│   ├── base.py            # common provider interface
│   ├── track17.py          # universal parcel tracking (17TRACK)
│   ├── cypost.py           # Cyprus Post parcel tracking (no key/login)
│   ├── imusic.py            # iMusic order status via ticket link (Playwright)
│   ├── store_generic.py    # template adapter for a store's order status
│   └── registry.py         # wires up all providers
├── requirements.txt
├── .env.example
├── .gitignore
└── .gitlab-ci.yml         # GitLab CI/CD pipeline (see "GitLab CI/CD" below)
```

## Limitations

- 17TRACK's free tier gives 100 tracking numbers per month.
- The store order-status adapter isn't a universal solution: each site
  needs its own setup and can break when the site's markup/protection
  changes.
- A notification is sent when the status changes relative to the previous
  run, and also on an order's first check (when the status is first added
  to the DB as a baseline).
