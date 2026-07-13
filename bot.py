"""Long-running Telegram bot for order tracking.

Runs on a server (e.g. a Google Cloud VM) via long polling: listens for
commands and re-checks all orders every CHECK_INTERVAL_MINUTES in the
background, messaging you when a status changes.

Commands (only work from TELEGRAM_CHAT_ID):
  /list                       — list tracked orders with their last status
  /add <number> [label]       — track a parcel by tracking number (17TRACK)
  /add <number> carrier:<id> [label]
                              — same, with an explicit 17TRACK carrier code
  /add <site>:<order_id> [label]
                              — track a store order (site = cypost, imusic, ...)
  /remove <n | number | key>  — stop tracking (n = index from /list)
  /check                      — force a check of all orders right now

Run: python bot.py   (see DEPLOY.md for the systemd service)
"""
import asyncio
import logging

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters

from config import load_config
from db import Database, order_key
from providers.registry import build_registry
from tracker import check_all, fetch_status, format_status, seed_orders_from_file

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("order-tracker")

config = load_config()
db = Database(config.db_path)
parcel_provider, store_providers = build_registry(config)

# /check and the scheduled check must not run at the same time.
check_lock = asyncio.Lock()

HELP = (
    "Commands:\n"
    "/list — tracked orders and their last status\n"
    "/add <tracking_number> [label] — track a parcel via 17TRACK\n"
    "/add <tracking_number> carrier:<code> [label] — pin a 17TRACK carrier\n"
    "/add <site>:<order_id> [label] — track a store order\n"
    f"    sites: {', '.join(sorted(store_providers))}\n"
    "/remove <n> — stop tracking (n = index from /list, or the number itself)\n"
    "/check — check all orders now"
)


# ----- command handlers -----

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Order tracker is running.\n\n" + HELP)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    orders = db.list_orders()
    if not orders:
        await update.message.reply_text("No orders tracked. Add one with /add.")
        return
    lines = []
    for i, order in enumerate(orders, 1):
        ident = order["tracking_number"] if order["kind"] == "parcel" \
            else f"{order['site']}:{order['order_id']}"
        status = db.get_status(order_key(order))
        status_text = "not checked yet"
        if status and status["last_status"]:
            status_text = status["last_status"] + (
                f" — {status['last_detail']}" if status["last_detail"] else ""
            )
        lines.append(f"{i}. {order['label']}\n    {ident}\n    {status_text}")
    await update.message.reply_text("\U0001F4E6 Tracked orders:\n\n" + "\n".join(lines))


def parse_add_args(args: list[str]) -> dict:
    """Builds an order dict from /add arguments. Raises ValueError on bad input."""
    if not args:
        raise ValueError(
            "Usage:\n/add <tracking_number> [label]\n"
            "/add <tracking_number> carrier:<code> [label]\n"
            "/add <site>:<order_id> [label]"
        )
    target, rest = args[0], list(args[1:])

    # store order:  <site>:<order_id>
    if ":" in target:
        site, _, order_id = target.partition(":")
        site = site.lower()
        if site not in store_providers:
            raise ValueError(
                f'Unknown site "{site}". Configured sites: {", ".join(sorted(store_providers))}'
            )
        if not order_id:
            raise ValueError(f"Usage: /add {site}:<order_id> [label]")
        label = " ".join(rest) or f"{site} {order_id}"
        return {"label": label, "kind": "store", "site": site, "order_id": order_id}

    # parcel:  <tracking_number> [carrier:<code>] [label]
    carrier_code = None
    if rest and rest[0].lower().startswith("carrier:"):
        raw = rest.pop(0).split(":", 1)[1]
        try:
            carrier_code = int(raw)
        except ValueError:
            raise ValueError(f'Carrier code must be a number (17TRACK id), got "{raw}"')
    label = " ".join(rest) or target
    return {
        "label": label,
        "kind": "parcel",
        "tracking_number": target,
        "carrier_code": carrier_code,
    }


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        order = parse_add_args(context.args)
        key = db.add_order(order)
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    await update.message.reply_text(f'Added "{order["label"]}". Checking…')

    # First check right away so the user immediately sees the status
    # (for parcels this also registers the number with 17TRACK).
    status_result, error = await fetch_status(order, parcel_provider, store_providers, True)
    if status_result is None:
        await update.message.reply_text(
            f"First check failed: {error}\n"
            "The order stays in the list and will be retried on the next scheduled check."
        )
        return
    db.set_status(key, order["label"], status_result.status, status_result.detail)
    text = status_result.status + (
        f" — {status_result.detail}" if status_result.detail else ""
    )
    await update.message.reply_text(f"\U0001F4E6 \"{order['label']}\":\n{text}")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /remove <n from /list, or tracking number>")
        return
    target = " ".join(context.args)
    orders = db.list_orders()

    key = None
    if target.isdigit() and 1 <= int(target) <= len(orders):
        key = order_key(orders[int(target) - 1])
    else:
        for order in orders:
            if target in (
                order_key(order), order.get("tracking_number"),
                order.get("order_id"), order["label"],
            ):
                key = order_key(order)
                break
    if key is None:
        await update.message.reply_text(
            f'"{target}" not found. Use /list and pass the item number.'
        )
        return

    label = db.get_order(key)["label"]
    db.remove_order(key)
    await update.message.reply_text(f'Removed "{label}".')


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not db.list_orders():
        await update.message.reply_text("No orders tracked. Add one with /add.")
        return
    if check_lock.locked():
        await update.message.reply_text("A check is already running, hold on…")
        return
    await update.message.reply_text("Checking all orders…")
    async with check_lock:
        results = await check_all(db, parcel_provider, store_providers)
    lines = []
    for r in results:
        mark = " (changed)" if r.changed else (" (new)" if r.first else "")
        lines.append(f"• {r.label}{mark}:\n    {format_status(r)}")
    await update.message.reply_text("\U0001F4E6 Check results:\n\n" + "\n".join(lines))


# ----- background scheduled check -----

async def scheduled_check(app: Application) -> None:
    interval = config.check_interval_minutes * 60
    logger.info("Background check every %s min", config.check_interval_minutes)
    while True:
        try:
            async with check_lock:
                results = await check_all(db, parcel_provider, store_providers)
            for r in results:
                if r.error:
                    continue
                if r.first:
                    await app.bot.send_message(
                        chat_id=config.chat_id,
                        text=f"\U0001F4E6 Now tracking \"{r.label}\":\n{format_status(r)}",
                    )
                elif r.changed:
                    await app.bot.send_message(
                        chat_id=config.chat_id,
                        text=f"\U0001F4E6 Status changed for \"{r.label}\":\n{format_status(r)}",
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled check failed; will retry next interval")
        await asyncio.sleep(interval)


async def post_init(app: Application) -> None:
    seed_orders_from_file(db)
    await app.bot.set_my_commands([
        BotCommand("list", "Tracked orders and their last status"),
        BotCommand("add", "Track a new order"),
        BotCommand("remove", "Stop tracking an order"),
        BotCommand("check", "Check all orders now"),
        BotCommand("help", "How to use the bot"),
    ])
    app.bot_data["check_task"] = asyncio.create_task(scheduled_check(app))


async def post_shutdown(app: Application) -> None:
    task = app.bot_data.get("check_task")
    if task:
        task.cancel()


def main() -> None:
    app = (
        Application.builder()
        .token(config.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Only react to the owner's chat — everyone else is ignored.
    owner = filters.Chat(chat_id=config.chat_id)
    app.add_handler(CommandHandler(["start", "help"], cmd_start, filters=owner))
    app.add_handler(CommandHandler("list", cmd_list, filters=owner))
    app.add_handler(CommandHandler("add", cmd_add, filters=owner))
    app.add_handler(CommandHandler("remove", cmd_remove, filters=owner))
    app.add_handler(CommandHandler("check", cmd_check, filters=owner))

    logger.info("Bot starting (long polling)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
