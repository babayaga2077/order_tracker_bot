"""One-shot script that checks order statuses from orders.py.

Not a long-running service and does not accept commands — meant to be run
on a schedule (cron / Windows Task Scheduler / CI), see README. On each
run:

1. reads the order list from orders.py (you edit it by hand);
2. fetches the current status of each order via the right provider;
3. compares it with the status saved in SQLite from the previous run;
4. if the status changed — sends a Telegram message;
5. saves the new status and exits.
"""
import asyncio
import logging

from telegram import Bot

from config import load_config
from db import Database
from orders import ORDERS
from providers.base import ProviderError
from providers.registry import build_registry

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logger = logging.getLogger("order-tracker")


def order_key(order: dict) -> str:
    """Stable identifier for an order, used as its status-history key in the DB."""
    if order.get("key"):
        return order["key"]
    if order["kind"] == "parcel":
        return f"parcel:{order['tracking_number']}"
    return f"store:{order['site']}:{order['order_id']}"


async def fetch_status(order: dict, parcel_provider, store_providers, is_first_check: bool):
    try:
        if order["kind"] == "parcel":
            provider = parcel_provider
            if provider is None:
                logger.warning('"%s": TRACK17_API_KEY is not set, skipping', order["label"])
                return None
            if is_first_check:
                # Register the tracking number with 17TRACK only on the first
                # check — after that it's already registered, no need to repeat.
                await provider.register(order["tracking_number"], order.get("carrier_code"))
        else:
            provider = store_providers.get(order["site"])
            if provider is None:
                logger.warning(
                    '"%s": site "%s" is not configured in providers/registry.py, skipping',
                    order["label"], order.get("site"),
                )
                return None
        return await provider.get_status(order)
    except ProviderError as exc:
        logger.warning('"%s": provider error: %s', order["label"], exc)
        return None
    except Exception:
        logger.exception('"%s": unexpected error while checking', order["label"])
        return None


async def main() -> None:
    config = load_config()
    db = Database(config.db_path)
    parcel_provider, store_providers = build_registry(config)
    bot = Bot(token=config.bot_token)

    if not ORDERS:
        logger.info("orders.py is empty — nothing to check.")
        return

    active_keys = [order_key(o) for o in ORDERS]
    removed = db.prune_missing(active_keys)
    if removed:
        logger.info("Removed %s order(s) no longer present in orders.py", removed)

    for order in ORDERS:
        key = order_key(order)
        previous = db.get_status(key)

        result = await fetch_status(order, parcel_provider, store_providers, previous is None)
        if result is None:
            continue

        db.set_status(key, order["label"], result.status, result.detail)
        text = result.status + (f" — {result.detail}" if result.detail else "")

        if previous is None:
            logger.info('"%s": first check, status: %s', order["label"], text)
            await bot.send_message(
                chat_id=config.chat_id,
                text=f"\U0001F4E6 Now tracking \"{order['label']}\":\n{text}",
            )
            continue

        changed = (
            result.status != previous["last_status"]
            or result.detail != (previous["last_detail"] or "")
        )
        if changed:
            prev_text = previous["last_status"] + (f" — {previous['last_detail']}" if previous["last_detail"] else "")
            logger.info('"%s": status changed: %s -> %s', order["label"], prev_text, text)
            await bot.send_message(
                chat_id=config.chat_id,
                text=f"\U0001F4E6 Status changed for \"{order['label']}\":\n{text}",
            )
        else:
            logger.info('"%s": no change (%s)', order["label"], text)


if __name__ == "__main__":
    asyncio.run(main())
