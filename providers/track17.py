"""Universal parcel tracking via the 17TRACK API v2.4.

17TRACK supports 3000+ carriers worldwide and can auto-detect the carrier
from the tracking number format — so this one adapter covers deliveries
from almost any site (Ozon, Wildberries, AliExpress, any overseas store,
etc.) as long as you have the shipment's tracking number.

Sign up and get a key: https://www.17track.net/en/api
(free — 100 tracking numbers/month on the trial tier).
Docs: https://api.17track.net/en/doc
"""
from typing import Optional

import httpx

from .base import BaseProvider, ProviderError, StatusResult

REGISTER_URL = "https://api.17track.net/track/v2.4/register"
INFO_URL = "https://api.17track.net/track/v2.4/gettrackinfo"

# "Already registered" error code — not a real error for us.
ALREADY_REGISTERED_CODE = -18019901


class Track17Provider(BaseProvider):
    name = "17track"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("TRACK17_API_KEY is not set")
        self.api_key = api_key
        self._headers = {"17token": api_key, "Content-Type": "application/json"}

    async def register(self, number: str, carrier: Optional[int] = None) -> None:
        """Registers a tracking number with 17TRACK. Needs to be done once
        before the first status request — without registration gettrackinfo
        returns an error."""
        payload = [{"number": number, **({"carrier": carrier} if carrier else {})}]
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(REGISTER_URL, headers=self._headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        rejected = data.get("data", {}).get("rejected", [])
        if rejected:
            err = rejected[0].get("error", {})
            if err.get("code") != ALREADY_REGISTERED_CODE:
                raise ProviderError(err.get("message", "Failed to register the tracking number"))

    async def get_status(self, order: dict) -> StatusResult:
        number = order["tracking_number"]
        carrier = order.get("carrier_code")
        payload = [{"number": number, **({"carrier": carrier} if carrier else {})}]
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(INFO_URL, headers=self._headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

        accepted = data.get("data", {}).get("accepted", [])
        if not accepted:
            rejected = data.get("data", {}).get("rejected", [])
            msg = rejected[0]["error"]["message"] if rejected else "tracking number not found in 17TRACK"
            raise ProviderError(msg)

        info = accepted[0].get("track_info", {})
        latest_status = info.get("latest_status") or {}
        latest_event = info.get("latest_event") or {}

        status = latest_status.get("status", "Unknown")
        sub_status = latest_status.get("sub_status") or ""
        description = latest_event.get("description") or ""
        detail = " — ".join(p for p in (sub_status, description) if p)
        return StatusResult(status=status, detail=detail)
