/**
 * ربات تلگرام صدور تصویر حواله صرافی
 * هماهنگ با Render.com و GitHub
 */

const { Telegraf, Markup } = require('telegraf');
const puppeteer = require('puppeteer');
const express = require('express');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

// ۱. بررسی توکن ربات
const BOT_TOKEN = process.env.BOT_TOKEN;
if (!BOT_TOKEN) {
  console.error('❌ خطا: مقدار BOT_TOKEN در متغیرهای محیطی (.env) یافت نشد!');
  process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);
const app = express();
const PORT = process.env.PORT || 3000;

// ۲. مدیریت پایگاه داده آدرس‌ها
const ADDRESS_FILE = path.join(__dirname, 'addresses.json');

const DEFAULT_ADDRESSES = [
  {
    id: 'kabul-1',
    province: 'کابل',
    keyword: 'کابل',
    fullAddress: 'کابل - سرای شهزاده منزل دوم دکان A161 صرافی شیراحمد',
    isDefault: true
  },
  {
    id: 'kandahar-1',
    province: 'کندهار',
    keyword: 'کندهار',
    fullAddress: 'کندهار - تجارتی مارکت منزل اول دکان 29 صرافی رفیع عزیزی',
    isDefault: false
  },
  {
    id: 'herat-1',
    province: 'هرات',
    keyword: 'هرات',
    fullAddress: 'هرات - صرافی مارکت خراسان منزل همکف دکان 12 صرافی پیمان',
    isDefault: false
  },
  {
    id: 'mazar-1',
    province: 'مزار شریف',
    keyword: 'مزار',
    fullAddress: 'مزار شریف - سرای کفایت طبقه اول دکان 45 صرافی آریا',
    isDefault: false
  }
];

function loadAddresses() {
  try {
    if (fs.existsSync(ADDRESS_FILE)) {
      const data = fs.readFileSync(ADDRESS_FILE, 'utf8');
      return JSON.parse(data);
    }
  } catch (err) {
    console.error('خطا در خواندن فایل آدرس‌ها:', err.message);
  }
  saveAddresses(DEFAULT_ADDRESSES);
  return DEFAULT_ADDRESSES;
}

function saveAddresses(addresses) {
  try {
    fs.writeFileSync(ADDRESS_FILE, JSON.stringify(addresses, null, 2), 'utf8');
  } catch (err) {
    console.error('خطا در ذخیره فایل آدرس‌ها:', err.message);
  }
}

let addressList = loadAddresses();

// ۳. تابع تبدیل تاریخ شمسی دقیق
function getTodayPersian() {
  try {
    const now = new Date();
    const weekdayFormatter = new Intl.DateTimeFormat('fa-AF-u-ca-persian', { weekday: 'long' });
    const dayName = weekdayFormatter.format(now);

    const partsFormatter = new Intl.DateTimeFormat('fa-AF-u-ca-persian', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    });

    const parts = partsFormatter.formatToParts(now);
    let year = '', month = '', day = '';
    for (const part of parts) {
      if (part.type === 'year') year = part.value;
      if (part.type === 'month') month = part.value;
      if (part.type === 'day') day = part.value;
    }
    return `${dayName} - ${year}/${month}/${day}`;
  } catch (e) {
    return 'دوشنبه - ۱۴۰۵/۰۷/۲۷';
  }
}

// ۴. تابع پردازش متن حواله (قانون خط چهارم)
function parseVoucher(text) {
  const lines = text.trim().split('\n').map(l => l.trim()).filter(l => l.length > 0);
  if (lines.length < 3) {
    return null;
  }

  // شماره حواله
  let num = lines[0];
  const numMatch = num.match(/(?:شماره|حواله|نمبر|no)?[:\s-]*([0-9\u06F0-\u06F9]+)/i);
  if (numMatch && numMatch[1]) {
    num = numMatch[1];
  } else {
    const parts = lines[0].split(/\s+/);
    if (parts.length >= 3 && !isNaN(Number(parts[2]))) {
      num = parts[2];
    }
  }

  // مبلغ
  const amount = lines[1].replace(/^مبلغ\s*[:\-]?\s*/i, '').trim();

  // فرستنده و گیرنده
  let sender = '';
  let receiver = '';
  const line3 = lines[2];
  if (line3.includes('برای')) {
    const p = line3.split('برای');
    sender = p[0].trim();
    receiver = p.slice(1).join('برای').trim();
  } else if (line3.includes('به نام')) {
    const p = line3.split('به نام');
    sender = p[0].trim();
    receiver = p.slice(1).join('به نام').trim();
  } else if (line3.includes('به')) {
    const p = line3.split('به');
    sender = p[0].trim();
    receiver = p.slice(1).join('به').trim();
  } else {
    sender = line3;
    receiver = '---';
  }

  sender = sender.replace(/^(?:فرستنده|از)\s*[:\-]?\s*/i, '').trim();
  receiver = receiver.replace(/^(?:گیرنده|به|نام)\s*[:\-]?\s*/i, '').trim();

  // قانون خط چهارم: انتخاب آدرس
  const defaultItem = addressList.find(a => a.isDefault) || addressList[0] || DEFAULT_ADDRESSES[0];
  let province = defaultItem.province;
  let address = defaultItem.fullAddress;

  if (lines.length >= 4) {
    const line4 = lines[3].trim().toLowerCase();
    let found = false;
    for (const item of addressList) {
      if (line4.includes(item.keyword.toLowerCase()) || line4.includes(item.province.toLowerCase())) {
        province = item.province;
        address = item.fullAddress;
        found = true;
        break;
      }
    }
    // اگر آدرس مستقیم تایپ شده بود
    if (!found && lines[3].trim().length > 10) {
      address = lines[3].trim();
      for (const item of addressList) {
        if (address.includes(item.province)) {
          province = item.province;
          break;
        }
      }
    }
  }

  return {
    province,
    date: getTodayPersian(),
    voucherNumber: num,
    amount,
    sender,
    receiver,
    address
  };
}

// ۵. تنظیمات فونت عنوان ربات (پیش‌فرض: تیتر)
let botTitleFont = 'titr'; // 'titr' یا 'nastaliq'

// قالب HTML جدول رسمی و شکیل صرافی
function getVoucherHTML(data, font = botTitleFont) {
  const isNastaliq = font === 'nastaliq';
  const headerFontFamily = isNastaliq
    ? "'IranNastaliq', 'Noto Nastaliq Urdu', 'Nastaliq', serif"
    : "'BTitr', 'Titr', 'Lalezar', 'Estedad', sans-serif";

  return `<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Lalezar&family=Noto+Nastaliq+Urdu:wght@400;700&family=Vazirmatn:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/gh/aminabedi68/Estedad-font@v2.0/dist/font-face.css" rel="stylesheet" type="text/css" />
<style>
@font-face {
    font-family: 'BTitr';
    src: url('https://cdn.jsdelivr.net/gh/rahatool/persian-fonts@master/packages/titr/dist/Titr.bold.woff2') format('woff2'),
         url('https://cdn.jsdelivr.net/gh/rahatool/persian-fonts@master/packages/titr/dist/Titr.bold.woff') format('woff'),
         local('B Titr'), local('Titr');
    font-weight: bold;
}
@font-face {
    font-family: 'IranNastaliq';
    src: url('https://cdn.jsdelivr.net/gh/rahatool/persian-fonts@master/packages/nastaliq/dist/Nastaliq.normal.woff2') format('woff2'),
         url('https://cdn.jsdelivr.net/gh/rahatool/persian-fonts@master/packages/nastaliq/dist/Nastaliq.normal.woff') format('woff'),
         local('IranNastaliq'), local('Iran Nastaliq');
    font-weight: normal;
}

*{box-sizing:border-box; margin:0; padding:0;}
body {
    font-family: 'Estedad', 'Vazirmatn', Tahoma, Arial, sans-serif;
    direction: rtl;
    background: transparent;
    display: inline-block;
    padding: 14px;
}
.voucher-card {
    width: 920px;
    background: #faf6ec;
    border: 3.5px solid #c9a13d;
    outline: 10px solid #0a1a30;
    outline-offset: -15px;
    border-radius: 20px;
    box-shadow: 0 30px 75px -10px rgba(0, 0, 0, 0.45);
    font-family: 'Estedad', 'Vazirmatn', Tahoma, sans-serif;
    color: #1b2330;
    overflow: hidden;
    direction: rtl;
}
table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    direction: rtl;
}
th {
    background: linear-gradient(135deg, #071526 0%, #0f2747 50%, #071526 100%);
    color: #fae19c;
    font-family: ${headerFontFamily};
    font-size: ${isNastaliq ? '52px' : '46px'};
    font-weight: ${isNastaliq ? '700' : '900'};
    line-height: ${isNastaliq ? '1.9' : '1.3'};
    padding: ${isNastaliq ? '28px 24px 22px' : '26px 24px 22px'};
    text-shadow: 0 3px 12px rgba(0, 0, 0, 0.65), 0 0 20px rgba(201, 161, 61, 0.2);
    border-bottom: 4px double #c9a13d;
    text-align: center;
}
.label {
    width: 35%;
    text-align: right;
    color: #0a1e36;
    font-size: 26px;
    font-weight: 800;
    border-left: 3px solid #b6a06a;
    border-bottom: 2.5px solid #b6a06a;
    background: linear-gradient(180deg, #f4ecd9 0%, #ece2c8 100%);
    padding: 22px 32px;
}
.value {
    text-align: right;
    color: #0f1a26;
    font-size: 33px;
    font-weight: 900;
    background: #faf6ec;
    border-bottom: 2.5px solid #b6a06a;
    padding: 22px 32px;
}
.footer {
    text-align: center;
    font-family: 'BTitr', 'Titr', 'Lalezar', 'Estedad', sans-serif;
    font-size: 32px;
    font-weight: 900;
    background: linear-gradient(180deg, #fbf6ea 0%, #ecdcb4 100%);
    border-top: 4px solid #c9a13d;
    padding: 26px 24px;
    color: #07182c;
    white-space: nowrap;
    letter-spacing: 0.4px;
    text-shadow: 0 1px 2px rgba(255, 255, 255, 0.8);
    box-shadow: inset 0 3px 8px rgba(201, 161, 61, 0.2);
}
</style>
</head>
<body>
  <div class="voucher-card" id="voucherCard">
    <table>
      <tr>
        <th colspan="2">مشخصات حواله \${data.province || 'کابل'}</th>
      </tr>
      <tr><td class="label">تاریخ</td><td class="value">\${data.date}</td></tr>
      <tr><td class="label">شماره حواله</td><td class="value">\${data.voucherNumber}</td></tr>
      <tr><td class="label">مبلغ</td><td class="value" style="font-size: 36px;">\${data.amount}</td></tr>
      <tr><td class="label">فرستنده</td><td class="value">\${data.sender}</td></tr>
      <tr><td class="label" style="border-bottom: none;">گیرنده</td><td class="value" style="border-bottom: none;">\${data.receiver}</td></tr>
      <tr><td colspan="2" class="footer"><span style="color: #dc2626; margin-left: 10px; font-size: 34px; vertical-align: middle;">📍</span><span style="vertical-align: middle;">\${data.address}</span></td></tr>
    </table>
  </div>
</body>
</html>`;
}

// ۶. تابع تبدیل HTML به تصویر با رزولوشن بالا و سرعت فوق‌العاده توسط Puppeteer
let browserInstance = null;

async function getBrowser() {
  if (!browserInstance || !browserInstance.isConnected()) {
    browserInstance = await puppeteer.launch({
      headless: 'new',
      executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--disable-accelerated-2d-canvas',
        '--no-first-run',
        '--no-zygote',
        '--single-process',
        '--disable-background-networking',
        '--disable-default-apps',
        '--disable-extensions',
        '--disable-sync',
        '--disable-translate',
        '--hide-scrollbars',
        '--metrics-recording-only',
        '--mute-audio',
        '--font-render-hinting=none'
      ]
    });
  }
  return browserInstance;
}

async function renderVoucherImage(voucherData, font = botTitleFont) {
  const browser = await getBrowser();
  let page = null;
  try {
    page = await browser.newPage();
    
    // بهینه‌سازی شبکه برای حداکثر سرعت رندر
    await page.setRequestInterception(true);
    page.on('request', (req) => {
      const type = req.resourceType();
      if (type === 'image' || type === 'font' || type === 'stylesheet' || type === 'document') {
        req.continue();
      } else {
        req.abort();
      }
    });

    // رزولوشن عالی با مقیاس ۲.۲ (کیفیت کریستالی و فوق‌العاده شفاف بدون کندی)
    await page.setViewport({ width: 1000, height: 840, deviceScaleFactor: 2.2 });
    const html = getVoucherHTML(voucherData, font);

    // استفاده از domcontentloaded برای حل کامل ارور Navigation timeout و تولید زیر ۲ ثانیه
    await page.setContent(html, {
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });

    // بررسی آمادگی فونت‌ها با تایم‌اوت ۱.۵ ثانیه تا ربات هرگز معطل نماند
    await page.evaluate(() => {
      return Promise.race([
        document.fonts.ready,
        new Promise((resolve) => setTimeout(resolve, 1500))
      ]);
    });

    const element = await page.$('#voucherCard');
    if (!element) {
      throw new Error('المنت کارت حواله در صفحه یافت نشد');
    }

    const buffer = await element.screenshot({
      type: 'jpeg',
      quality: 92,
      omitBackground: false
    });

    return buffer;
  } finally {
    if (page) {
      await page.close().catch(() => {});
    }
  }
}

// ۷. کیبورد اصلی ربات
const MAIN_KEYBOARD = Markup.keyboard([
  ['📋 لیست آدرس‌ها', '➕ افزودن آدرس'],
  ['❌ حذف آدرس', '⭐️ تعیین پیش‌فرض'],
  ['🔤 تغییر فونت عنوان', 'ℹ️ راهنمای ارسال حواله']
]).resize();

// وضعیت‌های کاربر برای ورودی متن‌های چندمرحله‌ای
const userState = new Map();

bot.start((ctx) => {
  ctx.reply(
    `سلام همکار گرامی! به ربات صدور حواله صرافی خوش آمدید 🏛️\n\n` +
    `برای صدور عکس حواله کافیست متن را با فرمت زیر بفرستید:\n\n` +
    `حواله شماره 467\nمبلغ 388 دالر\nهدایت الله برای عبدالرحیم\nکندهار (اختیاری: خط ۴ برای انتخاب آدرس)\n\n` +
    `فونت عنوان فعلی: *\${botTitleFont === 'titr' ? 'تیتر (B Titr)' : 'نستعلیق (IranNastaliq)'}*\n` +
    `از منوی زیر می‌توانید آدرس‌ها یا فونت را مدیریت نمایید:`,
    MAIN_KEYBOARD
  );
});

// مدیریت تغییر فونت عنوان (تیتر یا نستعلیق)
bot.hears('🔤 تغییر فونت عنوان', (ctx) => {
  const buttons = [
    [
      Markup.button.callback('🖋️ فونت تیتر (B Titr)', 'set_font_titr'),
      Markup.button.callback('✒️ خط نستعلیق (IranNastaliq)', 'set_font_nastaliq')
    ]
  ];
  ctx.reply(
    `فونت فعلی عنوان: *\${botTitleFont === 'titr' ? 'فونت تیتر (B Titr)' : 'خط نستعلیق'}*\n` +
    `لطفاً فونت دلخواه برای عنوان بالای سند حواله را انتخاب کنید:`,
    {
      parse_mode: 'Markdown',
      ...Markup.inlineKeyboard(buttons)
    }
  );
});

bot.action('set_font_titr', (ctx) => {
  botTitleFont = 'titr';
  ctx.answerCbQuery('فونت عنوان به تیتر تغییر یافت ✅');
  ctx.editMessageText('✅ فونت عنوان سند حواله با موفقیت به *فونت تیتر (B Titr)* تنظیم شد.', { parse_mode: 'Markdown' });
});

bot.action('set_font_nastaliq', (ctx) => {
  botTitleFont = 'nastaliq';
  ctx.answerCbQuery('فونت عنوان به نستعلیق تغییر یافت ✅');
  ctx.editMessageText('✅ فونت عنوان سند حواله با موفقیت به *خط نستعلیق (IranNastaliq)* تنظیم شد.', { parse_mode: 'Markdown' });
});

bot.hears('ℹ️ راهنمای ارسال حواله', (ctx) => {
  const defaultAddr = addressList.find(a => a.isDefault)?.province || 'کابل';
  ctx.reply(
    `📌 *راهنمای ارسال متن حواله:*\n\n` +
    `خط ۱: شماره حواله (مثلاً: شماره 467)\n` +
    `خط ۲: مبلغ و ارز (مثلاً: مبلغ 388 دالر)\n` +
    `خط ۳: فرستنده برای گیرنده (مثلاً: هدایت الله برای عبدالرحیم)\n` +
    `خط ۴: ولایت/آدرس صرافی (اختیاری)\n\n` +
    `💡 *قانون خط چهارم:* اگر خط چهارم نوشته نشود، خودکار به نام و آدرس *«${defaultAddr}»* صادر می‌شود. اگر بنویسید «کندهار»، «هرات» و ... آدرس همان شهر در پایین سند درج می‌شود.`,
    { parse_mode: 'Markdown' }
  );
});

// ۸. نمایش لیست آدرس‌ها
bot.hears('📋 لیست آدرس‌ها', (ctx) => {
  if (addressList.length === 0) {
    return ctx.reply('هیچ آدرسی ثبت نشده است! از دکمه «افزودن آدرس» استفاده کنید.');
  }
  let message = '📋 *لیست آدرس‌های فعال در ربات:*\n\n';
  addressList.forEach((item, index) => {
    const star = item.isDefault ? ' ⭐ (پیش‌فرض خط ۴)' : '';
    message += `*${index + 1}. ${item.province}*${star}\n`;
    message += `🔑 کلیدواژه خط چهارم: «${item.keyword}»\n`;
    message += `📍 ${item.fullAddress}\n\n`;
  });
  ctx.reply(message, { parse_mode: 'Markdown' });
});

// ۹. افزودن آدرس جدید
bot.hears('➕ افزودن آدرس', (ctx) => {
  userState.set(ctx.from.id, { step: 'WAITING_NEW_ADDRESS' });
  ctx.reply(
    `لطفاً مشخصات آدرس جدید را دقیقاً با خط جداکننده (|) در یک پیام ارسال فرمایید:\n\n` +
    `*فرمت:*\n` +
    `نام ولایت | کلیدواژه خط ۴ | متن کامل آدرس\n\n` +
    `*نمونه:*\n` +
    `نیمروز | نیمروز | زرنج - بازار صرافان دکان 14 صرافی برادران\n\n` +
    `(برای لغو، دستور /cancel را بفرستید)`,
    { parse_mode: 'Markdown' }
  );
});

// ۱۰. حذف آدرس با دکمه‌های شیشه‌ای
bot.hears('❌ حذف آدرس', (ctx) => {
  if (addressList.length <= 1) {
    return ctx.reply('حداقل یک آدرس باید در سیستم فعال باشد و امکان حذف آخرین آدرس نیست.');
  }
  const buttons = addressList.map(item => [
    Markup.button.callback(`🗑️ حذف ${item.province} (${item.keyword})`, `del_${item.id}`)
  ]);
  ctx.reply('روی هر آدرسی که می‌خواهید حذف شود کلیک کنید:', Markup.inlineKeyboard(buttons));
});

bot.action(/del_(.+)/, (ctx) => {
  const targetId = ctx.match[1];
  const item = addressList.find(a => a.id === targetId);
  if (!item) {
    return ctx.answerCbQuery('این آدرس یافت نشد!');
  }
  addressList = addressList.filter(a => a.id !== targetId);
  // اگر آدرس حذف شده پیش‌فرض بود، اولین مورد را پیش‌فرض کنیم
  if (item.isDefault && addressList.length > 0) {
    addressList[0].isDefault = true;
  }
  saveAddresses(addressList);
  ctx.answerCbQuery('آدرس با موفقیت حذف شد ✅');
  ctx.editMessageText(`✅ آدرس «${item.province}» با موفقیت حذف گردید.`);
});

// ۱۱. تعیین آدرس پیش‌فرض
bot.hears('⭐️ تعیین پیش‌فرض', (ctx) => {
  const buttons = addressList.map(item => [
    Markup.button.callback(`${item.isDefault ? '⭐ ' : ''}${item.province}`, `def_${item.id}`)
  ]);
  ctx.reply('کدام آدرس برای زمان‌هایی که خط چهارم خالی است پیش‌فرض باشد؟', Markup.inlineKeyboard(buttons));
});

bot.action(/def_(.+)/, (ctx) => {
  const targetId = ctx.match[1];
  addressList = addressList.map(a => ({
    ...a,
    isDefault: a.id === targetId
  }));
  saveAddresses(addressList);
  const picked = addressList.find(a => a.id === targetId);
  ctx.answerCbQuery('تنظیم شد ✅');
  ctx.editMessageText(`⭐ آدرس «${picked.province}» به عنوان پیش‌فرض خط چهارم ذخیره شد.`);
});

bot.command('cancel', (ctx) => {
  userState.delete(ctx.from.id);
  ctx.reply('عملیات لغو شد.', MAIN_KEYBOARD);
});

// ۱۲. دریافت پیام‌های متنی (حواله یا ثبت آدرس)
bot.on('text', async (ctx) => {
  const text = ctx.message.text.trim();
  const state = userState.get(ctx.from.id);

  // بررسی مرحله ثبت آدرس جدید
  if (state && state.step === 'WAITING_NEW_ADDRESS') {
    const parts = text.split('|').map(p => p.trim());
    if (parts.length < 3) {
      return ctx.reply('❌ فرمت اشتباه است. لطفاً ۳ بخش را با علامت | جدا کنید:\nنام ولایت | کلیدواژه | آدرس کامل');
    }
    const [province, keyword, fullAddress] = parts;
    const newId = 'addr_' + Date.now();
    addressList.push({
      id: newId,
      province,
      keyword,
      fullAddress,
      isDefault: false
    });
    saveAddresses(addressList);
    userState.delete(ctx.from.id);
    return ctx.reply(
      `✅ آدرس جدید با موفقیت اضافه شد:\n\n` +
      `📍 ولایت: ${province}\n` +
      `🔑 کلیدواژه خط چهارم: ${keyword}\n` +
      `🏢 آدرس: ${fullAddress}\n\n` +
      `از این پس اگر در خط چهارم «${keyword}» بنویسید این آدرس اعمال خواهد شد.`,
      MAIN_KEYBOARD
    );
  }

  // بررسی آیا متن حواله است
  const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
  if (lines.length >= 3) {
    const voucher = parseVoucher(text);
    if (!voucher) {
      return ctx.reply('فرمت متن شناخته نشد. لطفاً راهنما را مطالعه فرمایید.');
    }

    const waitMsg = await ctx.reply('⏳ در حال آماده‌سازی و رندر تصویر حواله با کیفیت اصلی...');
    try {
      const imageBuffer = await renderVoucherImage(voucher);
      await ctx.replyWithPhoto(
        { source: imageBuffer },
        {
          caption: `✅ حواله شماره ${voucher.voucherNumber} با موفقیت صادر شد.\n📍 ولایت: ${voucher.province}\n📅 تاریخ: ${voucher.date}`
        }
      );
      try {
        await ctx.deleteMessage(waitMsg.message_id);
      } catch (e) {}
    } catch (err) {
      console.error('خطا در تولید عکس:', err);
      ctx.reply('❌ متأسفانه در تولید عکس حواله خطایی رخ داد: ' + err.message);
    }
  }
});

// ۱۳. راه‌اندازی سرور وب جهت پاس کردن Healthcheck در Render.com
app.get('/', (req, res) => {
  res.send({
    status: 'online',
    service: 'Telegram Voucher Bot',
    uptime: process.uptime(),
    addressesCount: addressList.length
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Web service listening on port ${PORT} for Render healthcheck`);
});

// ۱۴. استارت ربات و پیش‌بارگذاری مرورگر برای پاسخ‌دهی صاعقه‌ای
bot.launch().then(() => {
  console.log('🤖 Telegram Bot is running successfully!');
  getBrowser().then(() => {
    console.log('⚡ Chromium browser pre-warmed and ready for instant voucher rendering!');
  }).catch((err) => {
    console.warn('⚠️ Browser pre-warming warning:', err.message);
  });
}).catch((err) => {
  console.error('❌ Failed to launch Telegram Bot:', err);
});

// مدیریت خروج تمیز
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
