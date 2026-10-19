import logging
import os
import re
from io import BytesIO

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, Update)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler,
                          filters)

import storage
from renderer import Renderer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("voucher-bot")

TOKEN = os.environ["BOT_TOKEN"]
ALLOWED = {int(x) for x in os.getenv("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x}
SEND_AS = os.getenv("SEND_AS", "both")  # photo | document | both

MENU_BTN = "📍 مدیریت آدرس‌ها"
KEYBOARD = ReplyKeyboardMarkup([[MENU_BTN]], resize_keyboard=True)
ASK_NAME, ASK_ADDRESS = range(2)

HELP = (
    "سلام 👋\n"
    "مشخصات حواله را در همین قالب بفرستید تا عکس آن را بسازم:\n\n"
    "حواله شماره 467\n"
    "مبلغ 388 دالر\n"
    "هدایت الله برای عبدالرحیم\n"
    "کابل\n\n"
    "• خط ۱: شماره حواله (سومین کلمه)\n"
    "• خط ۲: مبلغ\n"
    "• خط ۳: فرستنده «برای» گیرنده\n"
    "• خط ۴: نام آدرس (اختیاری؛ اگر نباشد آدرس پیش‌فرض)\n\n"
    "برای افزودن/حذف آدرس‌ها دکمهٔ «مدیریت آدرس‌ها» را بزنید."
)


def authorized(update: Update) -> bool:
    return not ALLOWED or (update.effective_user and update.effective_user.id in ALLOWED)


async def deny(update: Update):
    uid = update.effective_user.id if update.effective_user else "?"
    msg = f"⛔ دسترسی ندارید.\nشناسهٔ شما: {uid}"
    if update.callback_query:
        await update.callback_query.answer("دسترسی ندارید", show_alert=True)
    elif update.message:
        await update.message.reply_text(msg)


# ---------- پارس حواله ----------
def parse_voucher(text: str):
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 3:
        raise ValueError("لطفاً اطلاعات کامل حواله را وارد کنید.\n\n" + HELP)
    m = re.search(r"[0-9۰-۹]+", lines[0])
    toks = lines[0].split()
    num = m.group() if m else (toks[2] if len(toks) > 2 else lines[0])
    amount = lines[1].replace("مبلغ", "").strip()
    if "برای" not in lines[2]:
        raise ValueError("در خط سوم باید «فرستنده برای گیرنده» باشد.")
    sender, receiver = [p.strip() for p in lines[2].split("برای", 1)]
    addr = storage.find_for_line(lines[3] if len(lines) > 3 else "")
    return dict(province=addr["name"], num=num, amount=amount,
                sender=sender, receiver=receiver, address=addr["address"])


async def on_voucher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await deny(update)
    text = update.message.text or ""
    if text.strip() == MENU_BTN:
        return await show_addresses(update, context)
    try:
        data = parse_voucher(text)
    except ValueError as e:
        return await update.message.reply_text(str(e))
    wait = await update.message.reply_text("⏳ در حال ساخت عکس...")
    try:
        img = await context.application.bot_data["renderer"].render(**data)
    except Exception:
        log.exception("render failed")
        await wait.edit_text("❌ خطا در ساخت عکس. دوباره تلاش کنید.")
        return
    if SEND_AS in ("photo", "both"):
        await update.message.reply_photo(BytesIO(img))
    if SEND_AS in ("document", "both"):
        await update.message.reply_document(BytesIO(img), filename="voucher.jpg")
    await wait.delete()


# ---------- مدیریت آدرس‌ها ----------
def addresses_view():
    items = storage.load()
    lines = ["📍 آدرس‌های ثبت‌شده:\n"]
    rows = []
    for i in items:
        star = "⭐" if i.get("default") else "☆"
        lines.append(f"{star} {i['name']}\n{i['address']}\n")
        rows.append([
            InlineKeyboardButton(f"{star} {i['name']}", callback_data=f"set:{i['id']}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"del:{i['id']}"),
        ])
    rows.append([InlineKeyboardButton("➕ افزودن آدرس جدید", callback_data="add")])
    lines.append("ℹ️ اگر نام آدرس در خط چهارم حواله باشد همان آدرس استفاده می‌شود، "
                 "در غیر این صورت آدرس ⭐ پیش‌فرض.\n"
                 "برای پیش‌فرض کردن روی نام آدرس بزنید.")
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def show_addresses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await deny(update)
    text, kb = addresses_view()
    await update.effective_message.reply_text(text, reply_markup=kb)


async def on_addr_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await deny(update)
    q = update.callback_query
    action, _, addr_id = q.data.partition(":")
    if action == "set":
        storage.set_default(addr_id)
        await q.answer("پیش‌فرض شد ✅")
    elif action == "del":
        ok = storage.delete(addr_id)
        await q.answer("حذف شد 🗑" if ok else "حداقل یک آدرس باید بماند", show_alert=not ok)
    text, kb = addresses_view()
    try:
        await q.edit_message_text(text, reply_markup=kb)
    except Exception:
        pass


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        await deny(update)
        return ConversationHandler.END
    await update.callback_query.answer()
    await update.effective_message.reply_text(
        "نام آدرس را بفرستید (مثلاً: هرات).\n"
        "همین نام در خط چهارم حواله و در عنوان «مشخصات حواله …» استفاده می‌شود.\n"
        "اگر نام تکراری باشد، آدرس قبلی ویرایش می‌شود.\n\n/cancel برای انصراف")
    return ASK_NAME


async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_name"] = update.message.text.strip()
    await update.message.reply_text("حالا متن کامل آدرس را بفرستید (همان متنی که در پایین جدول 📍 می‌آید):")
    return ASK_ADDRESS


async def add_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage.upsert(context.user_data.pop("new_name"), update.message.text.strip())
    await update.message.reply_text("✅ ذخیره شد.")
    await show_addresses(update, context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("لغو شد.", reply_markup=KEYBOARD)
    return ConversationHandler.END


async def menu_in_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await show_addresses(update, context)
    return ConversationHandler.END


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await deny(update)
    await update.message.reply_text(HELP, reply_markup=KEYBOARD)


async def post_init(app: Application):
    r = Renderer()
    await r.start()
    app.bot_data["renderer"] = r


async def post_shutdown(app: Application):
    r = app.bot_data.get("renderer")
    if r:
        await r.stop()


def main():
    app = Application.builder().token(TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

    text_only = filters.TEXT & ~filters.COMMAND
    menu_filter = filters.Regex(re.escape(MENU_BTN))

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_start, pattern=r"^add$")],
        states={
            ASK_NAME: [MessageHandler(menu_filter, menu_in_conv), MessageHandler(text_only, add_name)],
            ASK_ADDRESS: [MessageHandler(menu_filter, menu_in_conv), MessageHandler(text_only, add_address)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("addresses", show_addresses))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(on_addr_button, pattern=r"^(set|del):"))
    app.add_handler(MessageHandler(text_only, on_voucher))

    base = os.getenv("RENDER_EXTERNAL_URL")
    if base:  # روی Render: وب‌هوک
        app.run_webhook(listen="0.0.0.0", port=int(os.getenv("PORT", "10000")),
                        url_path=TOKEN, webhook_url=f"{base.rstrip('/')}/{TOKEN}",
                        drop_pending_updates=True)
    else:  # لوکال: polling
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
