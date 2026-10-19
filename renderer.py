import asyncio
import html
import os
from pathlib import Path

from playwright.async_api import async_playwright

TEMPLATE = Path(__file__).with_name("template.html").read_text(encoding="utf-8")
# عرض عکس نمونه ≈ 2146 پیکسل روی جدول 900 پیکسلی  →  ضریب ≈ 2.4
SCALE = float(os.getenv("IMAGE_SCALE", "2.4"))


class Renderer:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def start(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(args=["--no-sandbox"])

    async def stop(self):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def render(self, province, num, amount, sender, receiver, address) -> bytes:
        e = html.escape
        page_html = (
            TEMPLATE.replace("{{PROVINCE}}", e(province))
            .replace("{{NUM}}", e(num))
            .replace("{{AMOUNT}}", e(amount))
            .replace("{{SENDER}}", e(sender))
            .replace("{{RECEIVER}}", e(receiver))
            .replace("{{ADDRESS}}", e(address))
        )
        async with self._lock:
            ctx = await self._browser.new_context(
                viewport={"width": 1000, "height": 1200},
                device_scale_factor=SCALE,
                timezone_id="Asia/Kabul",
                locale="fa-IR",
            )
            try:
                page = await ctx.new_page()
                page.set_default_timeout(45000)
                await page.set_content(page_html, wait_until="networkidle")
                await page.evaluate("document.fonts.ready.then(() => true)")
                await page.wait_for_timeout(150)
                return await page.locator("#voucherTable").screenshot(
                    type="jpeg", quality=100
                )
            finally:
                await ctx.close()
