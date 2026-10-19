import os
import io
import html
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

import telebot
from playwright.sync_api import sync_playwright

TOKEN = os.environ.get("BOT_TOKEN")

ADDRESSES = {
    "کابل": "کابل - سرای شهزاده منزل دوم دکان A161 صرافی شبیراحمد",
    "کندهار": "کندهار - تجارتی مارکت منزل اول دکان 29 صرافی رفیع عزیزی",
}

# ---------------------------------------------------------------- تاریخ شمسی
DAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]


def to_fa_digits(s):
    return str(s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100
            + (gy2 + 399) // 400 + gd + g_d_m[gm - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def get_today():
    now = datetime.now(ZoneInfo("Asia/Kabul"))
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    day_name = DAYS[(now.weekday() + 2) % 7]
    return to_fa_digits(f"{day_name} - {jy}/{jm:02d}/{jd:02d}")


# ------------------------------------------------- قالب HTML (همان طراحی شما)
PAGE = """<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="UTF-8">
<link href="https://cdn.jsdelivr.net/gh/aminabedi68/Estedad-font@v2.0/dist/font-face.css" rel="stylesheet">
<style>
@font-face{
  font-family:'LatinFix';
  src: local('Roboto Medium'), local('Roboto-Medium'), local('Roboto');
  unicode-range: U+0020-007E;
  font-weight:100 900;
}
:root{
  --navy-deep:#0a1a30; --navy:#0f2747; --gold:#c9a13d; --gold-light:#e6c66b;
  --paper:#faf6ec; --ink:#1b2330; --line:#b6a06a;
}
*{box-sizing:border-box}
body{ margin:0; background:#ffffff; direction:rtl;
  font-family:'LatinFix','Estedad',Tahoma,Arial,sans-serif; }
#voucherTable{
  width:900px; margin:18px auto; background:var(--paper);
  border:3px solid var(--gold); border-radius:16px;
  border-collapse:separate; border-spacing:0; padding:0;
  font-family:'LatinFix','Estedad',Tahoma,sans-serif;
  color:var(--ink); overflow:hidden; direction:rtl;
}
#voucherTable th{
  background:linear-gradient(135deg,#0a1a30 0%,#122c52 55%,#0a1a30 100%);
  color:var(--gold-light); font-size:38px; font-weight:800; line-height:1.5;
  padding:28px 28px 24px; text-shadow:0 2px 8px rgba(0,0,0,.45);
  border-bottom:4px double var(--gold); text-align:center;
}
#voucherTable td{
  background:transparent; border-bottom:2px solid var(--line);
  padding:24px 28px; font-size:32px; font-weight:700; line-height:1.6;
}
#voucherTable tr:last-of-type td{ border-bottom:none; }
.label{ width:36%; text-align:right; color:var(--navy); font-size:25px;
  font-weight:700; border-left:3px solid var(--line);
  background:linear-gradient(#f3ecd8,#efe7cf); }
.value{ text-align:right; color:var(--ink); font-size:32px; font-weight:800;
  background:var(--paper); }
.footer{ text-align:center; font-size:22px; font-weight:700;
  background:linear-gradient(#f6f1e3,#efe7d1)!important;
  border-top:3px solid var(--gold); white-space:nowrap; padding:22px 16px;
  color:var(--navy); }
</style></head><body>
<table id="voucherTable">
  <tr><th colspan="2">مشخصات حواله {province}</th></tr>
  <tr><td class="label">تاریخ</td><td class="value">{date}</td></tr>
  <tr><td class="label">شماره حواله</td><td class="value">{num}</td></tr>
  <tr><td class="label">مبلغ</td><td class="value">{amount}</td></tr>
  <tr><td class="label">فرستنده</td><td class="value">{sender}</td></tr>
  <tr><td class="label">گیرنده</td><td class="value">{receiver}</td></tr>
  <tr><td colspan="2" class="footer">📍 {address}</td></tr>
</table></body></html>"""


def build_html(province, num, amount, sender, receiver):
    e = html.escape
    return (PAGE
            .replace("{province}", e(province))
            .replace("{date}", e(get_today()))
            .replace("{num}", e(num))
            .replace("{amount}", e(amount))
            .replace("{sender}", e(sender))
            .replace("{receiver}", e(receiver))
            .replace("{address}", e(ADDRESSES[province])))


# --------------------------------------------------- عکس‌گرفتن با مرورگر
# (همه‌ی کارهای مرورگر باید در یک thread انجام شود، پس ربات threaded=False است)
_pw = None
_browser = None
_context = None


def get_context():
    global _pw, _browser, _context
    if _browser is None or not _browser.is_connected():
        if _pw is None:
            _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        _context = _browser.new_context(
            viewport={"width": 1000, "height": 900}, device_scale_factor=2)
    return _context


def reset_browser():
    global _browser, _context
    try:
        if _browser:
            _browser.close()
    except Exception:
        pass
    _browser = None
    _context = None


def make_voucher_image(province, num, amount, sender, receiver):
    page_html = build_html(province, num, amount, sender, receiver)
    last_err = None
    for _ in range(2):
        page = None
        try:
            page = get_context().new_page()
            page.set_content(page_html, wait_until="networkidle", timeout=40000)
            page.evaluate("document.fonts.ready.then(() => true)")
            data = page.locator("#voucherTable").screenshot(
                type="jpeg", quality=95)
            page.close()
            return io.BytesIO(data)
        except Exception as e:
            last_err = e
            reset_browser()
    raise last_err


# ------------------------------------------------------------ خواندن متن حواله
def parse(text):
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if len(lines) < 3:
        raise ValueError("اطلاعات کامل نیست")
    num = lines[0].split(" ")[2]
    amount = lines[1].replace("مبلغ", "").strip()
    sender, receiver = [p.strip() for p in lines[2].split("برای", 1)]
    province = "کندهار" if len(lines) > 3 and "کندهار" in lines[3] else "کابل"
    return province, num, amount, sender, receiver


# ----------------------------------------------------------------------- ربات
bot = telebot.TeleBot(TOKEN, threaded=False) if TOKEN else None

if bot:
    @bot.message_handler(commands=["start"])
    def start(m):
        bot.reply_to(m, "سلام 👋\nمتن حواله را بفرستید تا عکسش را بسازم.")

    @bot.message_handler(func=lambda m: True, content_types=["text"])
    def handle(m):
        try:
            data = parse(m.text)
        except Exception:
            bot.reply_to(m, "❌ لطفاً اطلاعات کامل حواله را بفرستید.")
            return
        try:
            photo = make_voucher_image(*data)
            bot.send_photo(m.chat.id, photo)
        except Exception as e:
            bot.reply_to(m, f"خطا در ساخت عکس: {e}")


# ----- یک سرور کوچک تا Render ربات را بیدار نگه دارد -----
class Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


def run_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), Ping).serve_forever()


if __name__ == "__main__":
    if not bot:
        raise SystemExit("BOT_TOKEN تنظیم نشده است")
    threading.Thread(target=run_server, daemon=True).start()
    print("ربات روشن شد")
    bot.infinity_polling(skip_pending=True)
