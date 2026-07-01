"""iMusic order status via the public ticket link
(https://imusic.co/ticket/<id>) — no login needed, the link itself grants
access to the order.

Important quirk: the site detects headless browsers (anti-bot) — a plain
headless Chromium gets a 403. The workaround is launching NOT in headless
mode (headless=False). For a fully non-interactive run (cron, Task
Scheduler, CI), wrap the command with a virtual display:

- Linux / GitHub Actions (ubuntu-latest): `xvfb-run -a python check_orders.py`
  (see the workflow example in README) — Chromium opens a window on a fake
  screen, the anti-bot sees no signs of headless mode, and the runner stays
  fully non-interactive.
- Windows: there's no xvfb, so the alternative is Task Scheduler with
  "Run only when user is logged on" (not "whether user is logged on or
  not"), so the visible window has a real desktop session to open in.

Also don't run the check too often — under frequent back-to-back requests
the site temporarily responds with 429 (Too many attempts).
"""
from playwright.async_api import async_playwright

from .base import BaseProvider, ProviderError, StatusResult

TICKET_URL_TEMPLATE = "https://imusic.co/ticket/{ticket_id}"
STATUS_SELECTOR = ".panel.panel-default.hidden-print .panel-heading.panel-title"


class ImusicProvider(BaseProvider):
    name = "imusic"

    async def get_status(self, order: dict) -> StatusResult:
        ticket_id = order["order_id"]
        url = TICKET_URL_TEMPLATE.format(ticket_id=ticket_id)
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                try:
                    page = await browser.new_page()
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    raw = await page.locator(STATUS_SELECTOR).first.inner_text(timeout=10000)
                finally:
                    await browser.close()
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Failed to read the iMusic order status: {exc}") from exc

        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:
            raise ProviderError("iMusic: empty status block — the site may have changed its markup")

        status = lines[0]
        detail = " ".join(lines[1:])
        return StatusResult(status=status, detail=detail)
