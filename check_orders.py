"""One-shot check of all orders (legacy mode).

The main way to run the tracker is now bot.py — a long-running bot that
listens for commands and checks on a schedule by itself. This script is
kept for cron / Windows Task Scheduler / CI setups: it checks every order
in the DB once, sends Telegram messages for changes, and exits.

The order list lives in the SQLite DB (managed via the bot's /add and
/remove commands). If a legacy orders.py is present, its entries are
imported into the DB on each run (already-imported ones are skipped).
"""
import asyncio
import logging

from telegram import Bot

from config import load_config
from db import Database
from providers.registry import build_registry
from tracker import check_all, format_status, seed_orders_from_file

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logger = logging.getLogger("order-tracker")


async def main() -> None:
    config = load_config()
    db = Database(config.db_path)
    parcel_provider, store_providers = build_registry(config)
    bot = Bot(token=config.bot_token)

    seed_orders_from_file(db)
    if not db.list_orders():
        logger.info("No orders in the DB — nothing to check.")
        return

    results = await check_all(db, parcel_provider, store_providers)
    for r in results:
        text = format_status(r)
        if r.error:
            continue
        if r.first:
            logger.info('"%s": first check, status: %s', r.label, text)
            await bot.send_message(
                chat_id=config.chat_id,
                text=f"\U0001F4E6 Now tracking \"{r.label}\":\n{text}",
            )
        elif r.changed:
            logger.info('"%s": status changed: %s', r.label, text)
            await bot.send_message(
                chat_id=config.chat_id,
                text=f"\U0001F4E6 Status changed for \"{r.label}\":\n{text}",
            )
        else:
            logger.info('"%s": no change (%s)', r.label, text)


if __name__ == "__main__":
    asyncio.run(main())
