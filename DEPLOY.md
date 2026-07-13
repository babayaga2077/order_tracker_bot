# Deploying on a Google Cloud VM (Ubuntu)

The bot runs as a systemd service: starts on boot, restarts on crashes,
logs to journald. Tested on Ubuntu 22.04/24.04.

## 1. Get the code onto the VM

```bash
sudo apt update && sudo apt install -y python3-venv git
sudo git clone <your-repo-url> /opt/order_tracker_bot
# or copy the folder from your PC:
# gcloud compute scp --recurse order_tracker_bot/ <vm-name>:/tmp/ && sudo mv /tmp/order_tracker_bot /opt/
```

## 2. Create a service user and a venv

```bash
sudo useradd --system --home /opt/order_tracker_bot --shell /usr/sbin/nologin tracker
cd /opt/order_tracker_bot
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt
```

If you use the `imusic` provider (or other Playwright-based adapters), also:

```bash
sudo venv/bin/playwright install --with-deps chromium
sudo apt install -y xvfb   # imusic runs Chromium non-headless — needs a virtual display
```

## 3. Configure

```bash
sudo cp .env.example .env
sudo nano .env        # fill in TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TRACK17_API_KEY
sudo chown -R tracker:tracker /opt/order_tracker_bot
sudo chmod 600 .env
```

`CHECK_INTERVAL_MINUTES` in `.env` controls how often the bot re-checks
everything in the background (default 30).

## 4. Install the systemd service

```bash
sudo cp deploy/order-tracker-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now order-tracker-bot
```

If you deployed to a different path or user, edit `User=`,
`WorkingDirectory=` and `ExecStart=` in the unit file first.

Using the `imusic` provider? Wrap the start command in a virtual display —
change `ExecStart=` to:

```
ExecStart=/usr/bin/xvfb-run -a /opt/order_tracker_bot/venv/bin/python bot.py
```

## 5. Manage it

```bash
sudo systemctl status order-tracker-bot          # is it running?
sudo journalctl -u order-tracker-bot -f          # live logs
sudo systemctl restart order-tracker-bot         # after changing code or .env
sudo systemctl stop order-tracker-bot
sudo systemctl disable order-tracker-bot         # remove from autostart
```

## 6. Use it from Telegram

Only messages from your `TELEGRAM_CHAT_ID` are accepted; everyone else is ignored.

```
/list                                  all tracked orders + last status
/add LP00123456789012 Headphones       parcel via 17TRACK (auto-detect carrier)
/add LV011239922CY carrier:190625 Ali  parcel with a pinned 17TRACK carrier code
/add cypost:LW541531090DE Eartips      store order via the cypost provider
/add imusic:<ticket-id> Vinyl          store order via the imusic provider
/remove 2                              remove item 2 from /list
/remove LP00123456789012               ...or by number/order id/label
/check                                 force a check of all orders right now
```

Status changes are pushed to you automatically every `CHECK_INTERVAL_MINUTES`.

## Notes

- The order list now lives in the SQLite DB (`orders.db`), managed by
  `/add` and `/remove`. A legacy `orders.py`, if present, is imported into
  the DB once at startup — after that you can delete it.
- `check_orders.py` still works as a one-shot cron-style check, but don't
  run it while the bot service is running — the bot already checks on its
  own schedule.
- No inbound ports are needed (the bot uses long polling), so no firewall
  rules to add on the VM.
- Back up `orders.db` if you rebuild the VM — it holds your order list.
