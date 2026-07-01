"""Template adapter for an order status shown DIRECTLY on a store's website
(Ozon, Wildberries, AliExpress, etc.), rather than via a parcel tracking
number.

An important limitation to understand: unlike 17TRACK, marketplaces don't
have an open public order-status API. To get the status you need to
emulate a logged-in user, and the markup and anti-bot protection (captchas,
bot-detection scripts) can change without notice — meaning this kind of
adapter will occasionally break and need fixing. This is not a turnkey
solution, it's a working template.

How to set it up for a specific site:
1. pip install playwright && playwright install chromium
2. Log in manually in a browser once and save the session:

       from playwright.sync_api import sync_playwright
       with sync_playwright() as p:
           browser = p.chromium.launch(headless=False)
           page = browser.new_page()
           page.goto("https://example.com/login")
           input("Log in in the opened window, then press Enter...")
           page.context.storage_state(path="site_state.json")

3. Point GENERIC_STORE_STATE_PATH (.env) at that file.
4. Replace ORDER_URL_TEMPLATE and STATUS_SELECTOR below with the real
   values for your site (check DevTools for which element holds the status).
5. For sites with their own quirks, it's easier to copy this file
   (e.g. ozon.py) and wire it up in providers/registry.py.
"""
from .base import BaseProvider, ProviderError, StatusResult

try:
    from playwright.async_api import async_playwright
except ImportError:  # playwright is optional until this adapter is actually used
    async_playwright = None


class GenericStoreProvider(BaseProvider):
    name = "generic-store"

    # TODO: replace with the real values for your site
    ORDER_URL_TEMPLATE = "https://example.com/my/orders/{order_id}"
    STATUS_SELECTOR = ".order-status"

    def __init__(self, storage_state_path: str):
        self.storage_state_path = storage_state_path

    async def get_status(self, order: dict) -> StatusResult:
        if async_playwright is None:
            raise ProviderError(
                "Playwright is not installed: pip install playwright && playwright install chromium"
            )
        url = self.ORDER_URL_TEMPLATE.format(order_id=order["order_id"])
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(storage_state=self.storage_state_path)
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle")
                try:
                    text = await page.locator(self.STATUS_SELECTOR).first.inner_text(timeout=10000)
                finally:
                    await browser.close()
        except ProviderError:
            raise
        except Exception as exc:  # site changed / session expired / anti-bot, etc.
            raise ProviderError(f"Failed to read the order status: {exc}") from exc

        return StatusResult(status=text.strip(), detail="")
