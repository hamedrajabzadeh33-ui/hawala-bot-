"""
ربات تلگرام صدور تصویر حواله صرافی با موتور پرسرعت پایتون (Pillow)
سرعت تولید زیر ۵۰ میلی‌ثانیه - مصرف حافظه کمتر از ۳۵ مگابایت - بدون نیاز به مرورگر کرومیوم
هماهنگ با Render.com و GitHub
"""

import os
import sys
import json
import io
import time
import threading
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# ۱. دریافت توکن ربات
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ خطا: متغیر BOT_TOKEN در متغیرهای محیطی یافت نشد!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
PORT = int(os.environ.get('PORT', 3000))

# ۲. مدیریت پایگاه داده آدرس‌ها
ADDRESS_FILE = os.path.join(os.path.dirname(__file__), 'addresses.json')

DEFAULT_ADDRESSES = [
    {
        "id": "kabul-1",
        "province": "کابل",
        "keyword": "کابل",
        "fullAddress": "کابل - سرای شهزاده منزل دوم دکان A161 صرافی شیراحمد",
        "isDefault": True
    },
    {
        "id": "kandahar-1",
        "province": "کندهار",
        "keyword": "کندهار",
        "fullAddress": "کندهار - تجارتی مارکت منزل اول دکان 29 صرافی رفیع عزیزی",
        "isDefault": False
    },
    {
        "id": "herat-1",
        "province": "هرات",
        "keyword": "هرات",
        "fullAddress": "هرات - صرافی مارکت خراسان منزل همکف دکان 12 صرافی پیمان",
        "isDefault": False
    },
    {
        "id": "mazar-1",
        "province": "مزار شریف",
        "keyword": "مزار",
        "fullAddress": "مزار شریف - سرای کفایت طبقه اول دکان 45 صرافی آریا",
        "isDefault": False
    }
]

def load_addresses():
    try:
        if os.path.exists(ADDRESS_FILE):
            with open(ADDRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading addresses: {e}")
    save_addresses(DEFAULT_ADDRESSES)
    return DEFAULT_ADDRESSES

def save_addresses(addrs):
    try:
        with open(ADDRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(addrs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving addresses: {e}")

address_list = load_addresses()

# ۳. دانلود خودکار فونت‌های فارسی Titr و Vazirmatn در صورت عدم وجود
FONTS_DIR = os.path.join(os.path.dirname(__file__), 'fonts')
os.makedirs(FONTS_DIR, exist_ok=True)
TITR_FONT_PATH = os.path.join(FONTS_DIR, 'BTitrBold.ttf')
VAZIR_FONT_PATH = os.path.join(FONTS_DIR, 'Vazirmatn-Bold.ttf')

def ensure_fonts():
    import urllib.request
    if not os.path.exists(TITR_FONT_PATH):
        try:
            print("⏳ Downloading Titr font for Python Pillow...")
            url = "https://raw.githubusercontent.com/font-store/b-titr/master/fonts/BTitrBold.ttf"
            urllib.request.urlretrieve(url, TITR_FONT_PATH)
            print("✅ Titr font ready.")
        except Exception as e:
            print(f"Warning downloading Titr font: {e}")
            
    if not os.path.exists(VAZIR_FONT_PATH):
        try:
            print("⏳ Downloading Vazirmatn font for Python Pillow...")
            url = "https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Bold.ttf"
            urllib.request.urlretrieve(url, VAZIR_FONT_PATH)
            print("✅ Vazirmatn font ready.")
        except Exception as e:
            print(f"Warning downloading Vazirmatn font: {e}")

ensure_fonts()

# ۴. الگوریتم استاندارد محاسبه تاریخ شمسی امروز
def get_today_persian():
    now = datetime.datetime.now()
    gy, gm, gd = now.year, now.month, now.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy - 1600 if gm > 2 else gy - 1601
    days = 365 * gy2 + (gy2 // 4) - (gy2 // 100) + (gy2 // 400) + g_d_m[gm - 1] + gd - 1
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    jm = 1 + (days // 31) if days < 186 else 7 + ((days - 186) // 30)
    jd = 1 + (days % 31 if days < 186 else (days - 186) % 30)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"

# ۵. آماده‌سازی متن فارسی برای رسم با Pillow
def fa(text):
    if not text:
        return ""
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return str(text)

# ۶. موتور رسم تصویر حواله با Pillow (فوق‌سریع - کمتر از ۵۰ میلی‌ثانیه)
def render_voucher_image_pil(data):
    W, H = 920, 800
    img = Image.new('RGB', (W, H), color='#0a1a30')
    draw = ImageDraw.Draw(img)

    # فونت‌ها
    try:
        font_header = ImageFont.truetype(TITR_FONT_PATH, 44)
    except Exception:
        font_header = ImageFont.load_default()

    try:
        font_label = ImageFont.truetype(VAZIR_FONT_PATH, 25)
        font_val = ImageFont.truetype(VAZIR_FONT_PATH, 31)
        font_val_large = ImageFont.truetype(VAZIR_FONT_PATH, 37)
        font_addr = ImageFont.truetype(TITR_FONT_PATH, 26)
    except Exception:
        font_label = font_val = font_val_large = font_addr = font_header

    # ۱. کارت اصلی با زمینه کاغذی کرم و کادر دوبل طلایی
    card_m = 16
    draw.rounded_rectangle(
        [(card_m, card_m), (W - card_m, H - card_m)],
        radius=22,
        fill='#faf6ec',
        outline='#c9a13d',
        width=4
    )

    # ۲. هدر سرمه‌ای شاهانه
    header_h = 105
    draw.rounded_rectangle(
        [(card_m + 3, card_m + 3), (W - card_m - 3, card_m + header_h)],
        radius=18,
        fill='#0a1a30',
        outline='#c9a13d',
        width=3
    )

    # عنوان هدر: مشخصات حواله [ولایت] با فونت تیتر طلایی و برجسته
    province = data.get('province') or 'کابل'
    header_title = fa(f"مشخصات حواله {province}")
    draw.text((W / 2, card_m + 52), header_title, fill='#f5df9e', font=font_header, anchor='mm')

    # ۳. رسم سطرهای جدول
    col_split = 630
    start_y = card_m + header_h
    row_h = 90
    rows = [
        ("تاریخ", data.get('date', '')),
        ("شماره حواله", data.get('voucherNumber', '')),
        ("مبلغ", data.get('amount', '')),
        ("فرستنده", data.get('sender', '')),
        ("گیرنده", data.get('receiver', ''))
    ]

    for i, (label, val) in enumerate(rows):
        y1 = start_y + i * row_h
        y2 = y1 + row_h
        row_bg = '#f4ecd7' if i % 2 == 1 else '#faf6ec'

        # زمینه سطر
        draw.rectangle([(card_m + 4, y1), (W - card_m - 4, y2)], fill=row_bg)

        # خط افقی طلایی بین سطرها
        draw.line([(card_m + 4, y2), (W - card_m - 4, y2)], fill='#bda364', width=2)

        # ستون راست: عنوان فیلد
        draw.text((col_split + 120, y1 + row_h / 2), fa(label), fill='#0a1e36', font=font_label, anchor='mm')

        # ستون چپ: مقدار فیلد
        v_font = font_val_large if label == "مبلغ" else font_val
        draw.text(((card_m + 4 + col_split) / 2, y1 + row_h / 2), fa(val), fill='#07182c', font=v_font, anchor='mm')

    # خط عمودی جداکننده ستون عنوان و مقدار
    table_bottom = start_y + len(rows) * row_h
    draw.line([(col_split, start_y), (col_split, table_bottom)], fill='#bda364', width=2)

    # ۴. فوتر آدرس: فونت تیتر بزرگ و پس‌زمینه زرین
    footer_y = table_bottom
    footer_h = (H - card_m - 4) - footer_y
    draw.rounded_rectangle(
        [(card_m + 4, footer_y + 2), (W - card_m - 4, H - card_m - 4)],
        radius=16,
        fill='#faeed2',
        outline='#c9a13d',
        width=3
    )

    full_addr = data.get('address') or ''
    addr_line = fa(f"📍 {full_addr}")
    draw.text((W / 2, footer_y + footer_h / 2), addr_line, fill='#07182c', font=font_addr, anchor='mm')

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=95)
    buf.seek(0)
    return buf

# ۷. پارسر متن حواله صرافی
def parse_voucher(text):
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    if len(lines) < 3:
        return None
        
    num = lines[0].replace('حواله', '').replace('شماره', '').replace(':', '').replace('-', '').strip()
    amt = lines[1].replace('مبلغ', '').replace(':', '').replace('-', '').strip()

    line3 = lines[2]
    if 'برای' in line3:
        p = line3.split('برای', 1)
        sender, receiver = p[0].strip(), p[1].strip()
    elif 'به نام' in line3:
        p = line3.split('به نام', 1)
        sender, receiver = p[0].strip(), p[1].strip()
    elif 'به' in line3:
        p = line3.split('به', 1)
        sender, receiver = p[0].strip(), p[1].strip()
    else:
        sender, receiver = line3.strip(), '---'

    sender = sender.replace('فرستنده', '').replace('از', '').replace(':', '').strip()
    receiver = receiver.replace('گیرنده', '').replace('به', '').replace(':', '').strip()

    # قانون خط چهارم
    default_item = next((a for a in address_list if a.get('isDefault')), address_list[0] if address_list else DEFAULT_ADDRESSES[0])
    province = default_item['province']
    address = default_item['fullAddress']

    if len(lines) >= 4:
        line4 = lines[3].lower()
        found = False
        for item in address_list:
            if item['keyword'].lower() in line4 or item['province'].lower() in line4:
                province = item['province']
                address = item['fullAddress']
                found = True
                break
        if not found and len(lines[3]) > 10:
            address = lines[3]
            for item in address_list:
                if item['province'] in address:
                    province = item['province']
                    break

    return {
        'province': province,
        'date': get_today_persian(),
        'voucherNumber': num,
        'amount': amt,
        'sender': sender,
        'receiver': receiver,
        'address': address
    }

# ۸. کیبورد اصلی ربات
MAIN_KEYBOARD = types.ReplyKeyboardMarkup(resize_keyboard=True)
MAIN_KEYBOARD.row('📋 لیست آدرس‌ها', '➕ افزودن آدرس')
MAIN_KEYBOARD.row('❌ حذف آدرس', '⭐️ تعیین پیش‌فرض')
MAIN_KEYBOARD.row('ℹ️ راهنمای ارسال حواله')

user_states = {}

@bot.message_handler(commands=['start'])
def handle_start(message):
    welcome_text = (
        "سلام همکار گرامی! به ربات صدور حواله صرافی خوش آمدید 🏛️\n\n"
        "⚡ *موتور پرسرعت پایتون:* ارسال عکس در کمتر از ۱ ثانیه!\n\n"
        "برای صدور سند کافیست مشخصات را با فرمت زیر بفرستید:\n\n"
        "```text\n"
        "حواله شماره 467\n"
        "مبلغ 388 دالر\n"
        "هدایت الله برای عبدالرحیم\n"
        "کندهار (اختیاری: خط ۴ برای انتخاب آدرس)\n"
        "```\n\n"
        "از دکمه‌های زیر می‌توانید آدرس‌ها را مدیریت نمایید:"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)

@bot.message_handler(func=lambda m: m.text == '📋 لیست آدرس‌ها')
def handle_list_addresses(message):
    msg = "📋 *لیست آدرس‌های فعال در سیستم:*\n\n"
    for idx, item in enumerate(address_list):
        star = " ⭐ (پیش‌فرض خط ۴)" if item.get('isDefault') else ""
        msg += f"*{idx + 1}. {item['province']}*{star}\n"
        msg += f"🔑 کلیدواژه خط ۴: «{item['keyword']}»\n"
        msg += f"📍 {item['fullAddress']}\n\n"
    bot.send_message(message.chat.id, msg, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)

@bot.message_handler(func=lambda m: m.text == '➕ افزودن آدرس')
def handle_add_address(message):
    user_states[message.from_user.id] = 'WAITING_ADD'
    prompt = (
        "لطفاً مشخصات آدرس جدید را با خط عمودی (|) ارسال نمایید:\n\n"
        "*فرمت:*\n"
        "`نام ولایت | کلیدواژه | آدرس کامل`\n\n"
        "*نمونه:*\n"
        "`نیمروز | نیمروز | زرنج بازار صرافان دکان 14 صرافی برادران`\n\n"
        "(برای انصراف /cancel بفرستید)"
    )
    bot.send_message(message.chat.id, prompt, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '❌ حذف آدرس')
def handle_del_address(message):
    if len(address_list) <= 1:
        bot.send_message(message.chat.id, "حداقل یک آدرس باید در سیستم باقی بماند.")
        return
    markup = types.InlineKeyboardMarkup()
    for item in address_list:
        btn = types.InlineKeyboardButton(f"🗑️ حذف {item['province']} ({item['keyword']})", callback_data=f"del_{item['id']}")
        markup.add(btn)
    bot.send_message(message.chat.id, "روی آدرسی که می‌خواهید حذف شود بزنید:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '⭐️ تعیین پیش‌فرض')
def handle_set_default(message):
    markup = types.InlineKeyboardMarkup()
    for item in address_list:
        prefix = "⭐ " if item.get('isDefault') else ""
        btn = types.InlineKeyboardButton(f"{prefix}{item['province']}", callback_data=f"def_{item['id']}")
        markup.add(btn)
    bot.send_message(message.chat.id, "کدام آدرس برای خط چهارم خالی، پیش‌فرض باشد؟", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_') or call.data.startswith('def_'))
def handle_callbacks(call):
    global address_list
    data = call.data
    if data.startswith('del_'):
        target_id = data.replace('del_', '')
        item = next((a for a in address_list if a['id'] == target_id), None)
        if item:
            address_list = [a for a in address_list if a['id'] != target_id]
            if item.get('isDefault') and address_list:
                address_list[0]['isDefault'] = True
            save_addresses(address_list)
            bot.answer_callback_query(call.id, "آدرس با موفقیت حذف شد.")
            bot.edit_message_text(f"✅ آدرس «{item['province']}» با موفقیت حذف شد.", call.message.chat.id, call.message.message_id)
    elif data.startswith('def_'):
        target_id = data.replace('def_', '')
        for a in address_list:
            a['isDefault'] = (a['id'] == target_id)
        save_addresses(address_list)
        picked = next((a for a in address_list if a['id'] == target_id), None)
        bot.answer_callback_query(call.id, "تنظیم شد.")
        bot.edit_message_text(f"⭐ آدرس «{picked['province']}» پیش‌فرض خط چهارم شد.", call.message.chat.id, call.message.message_id)

@bot.message_handler(commands=['cancel'])
def handle_cancel(message):
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "عملیات لغو شد.", reply_markup=MAIN_KEYBOARD)

@bot.message_handler(func=lambda m: m.text == 'ℹ️ راهنمای ارسال حواله')
def handle_help(message):
    help_text = (
        "📌 *راهنمای ارسال متن حواله:*\n\n"
        "خط ۱: شماره حواله (مثلاً: شماره 467)\n"
        "خط ۲: مبلغ و ارز (مثلاً: مبلغ 388 دالر)\n"
        "خط ۳: فرستنده برای گیرنده (مثلاً: هدایت الله برای عبدالرحیم)\n"
        "خط ۴: ولایت یا آدرس (اختیاری)\n\n"
        "💡 *قانون خط چهارم:*\n"
        "اگر خط چهارم خالی باشد، آدرس پیش‌فرض سیستم اعمال می‌شود.\n"
        "اگر نام ولایتی مانند «کندهار» یا «هرات» نوشته شود، آدرس همان شهر در پایین سند درج خواهد شد."
    )
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)

# پردازش پیام‌های دریافتی (افزودن آدرس یا صدور حواله)
@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    text = message.text.strip()
    user_id = message.from_user.id

    if user_states.get(user_id) == 'WAITING_ADD':
        parts = [p.strip() for p in text.split('|')]
        if len(parts) < 3:
            bot.send_message(message.chat.id, "❌ فرمت اشتباه است. لطفاً ۳ بخش را با علامت | جدا کنید:\nولایت | کلیدواژه | آدرس کامل")
            return
        prov, kw, faddr = parts[0], parts[1], parts[2]
        new_item = {
            "id": f"addr_{int(time.time())}",
            "province": prov,
            "keyword": kw,
            "fullAddress": faddr,
            "isDefault": False
        }
        address_list.append(new_item)
        save_addresses(address_list)
        user_states.pop(user_id, None)
        bot.send_message(message.chat.id, f"✅ آدرس جدید «{prov}» با کلیدواژه «{kw}» ذخیره شد.", reply_markup=MAIN_KEYBOARD)
        return

    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if len(lines) >= 3:
        voucher = parse_voucher(text)
        if not voucher:
            bot.send_message(message.chat.id, "فرمت متن شناخته نشد. لطفاً از دکمه راهنما استفاده کنید.")
            return

        wait_msg = bot.send_message(message.chat.id, "⏳ در حال صدور تصویر حواله...")
        t0 = time.time()
        try:
            image_buffer = render_voucher_image_pil(voucher)
            elapsed = time.time() - t0
            caption = (
                f"✅ حواله شماره {voucher['voucherNumber']} صادر شد.\n"
                f"📍 ولایت: {voucher['province']}\n"
                f"📅 تاریخ: {voucher['date']}\n"
                f"⚡ زمان تولید: {elapsed:.2f} ثانیه"
            )
            bot.send_photo(message.chat.id, photo=image_buffer, caption=caption)
            try:
                bot.delete_message(message.chat.id, wait_msg.message_id)
            except Exception:
                pass
        except Exception as e:
            print(f"Error rendering image: {e}")
            bot.send_message(message.chat.id, f"❌ متأسفانه در تولید عکس خطایی رخ داد: {str(e)}")

# ۹. وب‌سرور سبک داخلی جهت پاس کردن Healthcheck در Render.com
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        resp = {"status": "online", "engine": "Python Pillow Ultra-Fast", "uptime": time.time()}
        self.wfile.write(json.dumps(resp).encode('utf-8'))
        
    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
    print(f"🌐 Python Health server listening on port {PORT} for Render.com")
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ۱۰. راه‌اندازی ربات با قابلیت راه‌اندازی مجدد خودکار در صورت قطعی اینترنت
print("🚀 Telegram Voucher Bot (Python) is starting polling...")
while True:
    try:
        bot.infinity_polling(timeout=20, long_polling_timeout=15)
    except Exception as e:
        print(f"⚠️ Polling reconnecting: {e}")
        time.sleep(3)
