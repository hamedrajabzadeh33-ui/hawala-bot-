import os
import io
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

import telebot
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

TOKEN = os.environ.get("BOT_TOKEN")
FONT_PATH = os.path.join(os.path.dirname(__file__), "font.ttf")

# رنگ‌ها (همان رنگ‌های کد HTML شما)
NAVY_DEEP = "#0a1a30"
NAVY = "#0f2747"
GOLD = "#c9a13d"
GOLD_LIGHT = "#e6c66b"
PAPER = "#faf6ec"
INK = "#1b2330"
LINE = "#b6a06a"
LABEL_BG = PAPER

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


# ------------------------------------------------------------ رسم متن فارسی
def fix(text):
    return get_display(arabic_reshaper.reshape(text))


def draw_rtl(draw, xy, text, font, fill):
    # xy = گوشه بالا-راست متن
    draw.text(xy, fix(text), font=font, fill=fill, anchor="ra")


def load_font(size):
    return ImageFont.truetype(FONT_PATH, size, layout_engine=ImageFont.Layout.BASIC)


def text_width(draw, text, font):
    return draw.textlength(fix(text), font=font)


def wrap(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if text_width(draw, test, font) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


# ------------------------------------------------------------------ ساخت عکس
def make_voucher_image(province, num, amount, sender, receiver):
    S = 2  # ضریب کیفیت
    W = 900 * S
    pad = 28 * S
    f_head = load_font(38 * S)
    f_label = load_font(25 * S)
    f_value = load_font(32 * S)
    f_foot = load_font(22 * S)

    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    label_w = int(W * 0.36)
    value_max = W - label_w - 2 * pad

    rows = [
        ("تاریخ", get_today()),
        ("شماره حواله", num),
        ("مبلغ", amount),
        ("فرستنده", sender),
        ("گیرنده", receiver),
    ]

    # ارتفاع هر ردیف (اگر متن بلند بود چند خطی می‌شود)
    line_h = int(32 * S * 1.6)
    laid = []
    for label, value in rows:
        lines = wrap(tmp, value, f_value, value_max)
        h = max(2 * pad + line_h * len(lines), 2 * pad + int(25 * S * 1.6))
        laid.append((label, lines, h))

    head_h = int(38 * S * 1.5) + 52 * S
    foot_h = int(22 * S * 1.6) + 44 * S
    H = head_h + sum(h for _, _, h in laid) + foot_h

    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # هدر
    mid = "#122c52"
    for x in range(W):
        t = 1 - abs(x - W / 2) / (W / 2)  # 0 در لبه‌ها، 1 در وسط
        c0 = tuple(int(NAVY_DEEP[i:i + 2], 16) for i in (1, 3, 5))
        c1 = tuple(int(mid[i:i + 2], 16) for i in (1, 3, 5))
        col = tuple(int(c0[k] + (c1[k] - c0[k]) * t) for k in range(3))
        d.line([x, 0, x, head_h], fill=col)
    d.line([0, head_h - 4 * S, W, head_h - 4 * S], fill=GOLD, width=S)
    d.line([0, head_h, W, head_h], fill=GOLD, width=S * 2)
    title = f"مشخصات حواله {province}"
    draw_rtl(d, (W // 2 + text_width(d, title, f_head) / 2,
                 (head_h - int(38 * S * 1.5)) // 2 + 4 * S),
             title, f_head, GOLD_LIGHT)

    # ردیف‌ها
    y = head_h
    for label, lines, h in laid:
        # ستون برچسب (سمت راست)
        d.rectangle([W - label_w, y, W, y + h], fill=LABEL_BG)
        d.line([W - label_w, y, W - label_w, y + h], fill=LINE, width=3 * S)
        d.line([0, y + h, W, y + h], fill=LINE, width=2 * S)
        draw_rtl(d, (W - pad, y + h // 2 - 20 * S), label, f_label, NAVY)
        ty = y + pad
        for ln in lines:
            draw_rtl(d, (W - label_w - pad, ty), ln, f_value, INK)
            ty += line_h
        y += h

    # فوتر (آدرس)
    d.rectangle([0, y, W, H], fill="#f2ecdb")
    d.line([0, y, W, y], fill=GOLD, width=3 * S)
    addr = ADDRESSES[province]
    fw = text_width(d, addr, f_foot)
    pin_w = 30 * S
    total = fw + pin_w
    right = W // 2 + total / 2
    cy = y + foot_h // 2
    # آیکن سنجاق قرمز
    px = right - 12 * S
    d.polygon([(px - 8 * S, cy - 4 * S), (px + 8 * S, cy - 4 * S),
               (px, cy + 18 * S)], fill="#9fb4c4")
    d.ellipse([px - 11 * S, cy - 20 * S, px + 11 * S, cy + 2 * S], fill="#e53935")
    draw_rtl(d, (right - pin_w, y + 22 * S), addr, f_foot, NAVY)

    # قاب‌ها
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=16 * S,
                        outline=GOLD, width=3 * S)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    buf.seek(0)
    return buf


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
bot = telebot.TeleBot(TOKEN) if TOKEN else None

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
