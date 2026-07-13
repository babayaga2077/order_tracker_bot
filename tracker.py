"""Shared order-checking logic, used by both the long-running bot (bot.py)
and the legacy one-shot script (check_orders.py).

The order list lives in the SQLite DB (see db.py); the bot's /add and
/remove commands edit it. On first run the DB is seeded from orders.py
if that file still exists (legacy hand-edited list)."""
import logging
from dataclasses import dataclass
from typing import Optional

from db import Database, order_key
from providers.base import ProviderError

logger = logging.getLogger("order-tracker")


@dataclass
class CheckResult:
    key: str
    label: str
    status: Optional[str]       # None if the check failed
    detail: str
    changed: bool               # status differs from the previous run
    first: bool                 # first ever check of this order
    error: Optional[str] = None


def seed_orders_from_file(db: Database) -> int:
    """Imports orders from the legacy orders.py into the DB (once; entries
    already in the DB are skipped). Returns the number of imported orders."""
    try:
        from orders import ORDERS  # type: ignore
    except ImportError:
        return 0
    if not ORDERS:
        return 0
    added = db.seed_from_list(ORDERS)
    if added:
        logger.info("Imported %s order(s) from orders.py into the DB", added)
    return added


async def fetch_status(order: dict, parcel_provider, store_providers, is_first_check: bool):
    """Returns (StatusResult | None, error_message | None)."""
    try:
        if order["kind"] == "parcel":
            provider = parcel_provider
            if provider is None:
                return None, "TRACK17_API_KEY is not set"
            if is_first_check:
                # Register the tracking number with 17TRACK only on the first
                # check — after that it's already registered, no need to repeat.
                await provider.register(order["tracking_number"], order.get("carrier_code"))
        else:
            provider = store_providers.get(order["site"])
            if provider is None:
                return None, f'site "{order.get("site")}" is not configured in providers/registry.py'
        return await provider.get_status(order), None
    except ProviderError as exc:
        return None, str(exc)
    except Exception as exc:
        logger.exception('"%s": unexpected error while checking', order["label"])
        return None, f"unexpected error: {exc}"


async def check_all(db: Database, parcel_provider, store_providers) -> list[CheckResult]:
    """Checks every order in the DB, updates stored statuses and returns the
    per-order results. Does NOT send any Telegram messages — the caller
    decides what to report."""
    results: list[CheckResult] = []
    for order in db.list_orders():
        key = order_key(order)
        previous = db.get_status(key)

        status_result, error = await fetch_status(
            order, parcel_provider, store_providers, previous is None
        )
        if status_result is None:
            logger.warning('"%s": %s', order["label"], error)
            results.append(CheckResult(
                key=key, label=order["label"], status=None, detail="",
                changed=False, first=previous is None, error=error,
            ))
            continue

        db.set_status(key, order["label"], status_result.status, status_result.detail)

        first = previous is None
        changed = not first and (
            status_result.status != previous["last_status"]
            or status_result.detail != (previous["last_detail"] or "")
        )
        results.append(CheckResult(
            key=key, label=order["label"], status=status_result.status,
            detail=status_result.detail, changed=changed, first=first,
        ))
    return results


def format_status(r: CheckResult) -> str:
    if r.error:
        return f"check failed: {r.error}"
    return r.status + (f" — {r.detail}" if r.detail else "")
