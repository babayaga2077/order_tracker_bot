"""Tracks Cyprus Post parcels directly via the official tracker
(http://ips.cypruspost.gov.cy/ipswebtrack/) — no API key or login needed,
just the shipment number. Useful when 17TRACK hasn't picked up the status
yet (e.g. the parcel already arrived in Cyprus but 17TRACK syncs with a
delay), or when the tracking number isn't covered by 17TRACK at all.

There's no public JSON API for this service, so the results HTML table is
parsed by hand — if Cyprus Post changes the page markup, parsing will
break and get_status will raise a ProviderError with a clear message.
"""
import html
import re

import httpx

from .base import BaseProvider, ProviderError, StatusResult

TRACK_URL = "http://ips.cypruspost.gov.cy/ipswebtrack/IPSWeb_item_events.aspx"
NOT_FOUND_MARKER = "please check your item identifier"

ROW_RE = re.compile(r'<tr class="tabl[12]">(.*?)</tr>', re.S)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def _clean(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", cell)).strip()


class CyprusPostProvider(BaseProvider):
    name = "cypost"

    async def get_status(self, order: dict) -> StatusResult:
        number = order.get("tracking_number") or order["order_id"]
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(TRACK_URL, params={"itemid": number})
        resp.raise_for_status()
        text = resp.text

        if NOT_FOUND_MARKER in text:
            raise ProviderError(f'Cyprus Post: tracking number "{number}" not found')

        rows = ROW_RE.findall(text)
        if not rows:
            raise ProviderError("Cyprus Post: failed to parse the tracking page (markup changed?)")

        cells = [_clean(cell) for cell in CELL_RE.findall(rows[-1])]
        if len(cells) < 6:
            raise ProviderError("Cyprus Post: unexpected event row format")

        date, country, location, event_type, _mail_category, next_office, *extra = cells
        extra_text = " ".join(p for p in extra if p)

        detail_bits = [date]
        place = ", ".join(p for p in (location, country) if p)
        if place:
            detail_bits.append(place)
        if next_office and next_office != "-":
            detail_bits.append(f"next office: {next_office}")
        if extra_text:
            detail_bits.append(extra_text)

        return StatusResult(status=event_type or "Unknown", detail=" — ".join(detail_bits))
