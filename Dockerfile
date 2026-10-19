# ایمیج پایه Node.js نسخه 20 بر بستر Debian Slim
FROM node:20-slim

# نصب ابزارهای موردنیاز و وابستگی‌های اجرای کرومیوم به همراه فونت‌های فارسی
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-ipafont-gothic \
    fonts-wqy-zenhei \
    fonts-thai-tlwg \
    fonts-kacst \
    fonts-freefont-ttf \
    fonts-noto-core \
    fonts-noto-extra \
    fonts-noto-cjk \
    ca-certificates \
    curl \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# دانلود مستقیم فونت‌های فارسی Titr و Estedad برای کش آفلاین و سرعت فوق‌العاده
RUN mkdir -p /usr/share/fonts/truetype/persian && \
    curl -fsSL https://cdn.jsdelivr.net/gh/rahatool/persian-fonts@master/packages/titr/dist/Titr.bold.woff -o /usr/share/fonts/truetype/persian/Titr.bold.woff || true && \
    curl -fsSL https://cdn.jsdelivr.net/gh/aminabedi68/Estedad-font@v2.0/dist/woff2/Estedad-Bold.woff2 -o /usr/share/fonts/truetype/persian/Estedad-Bold.woff2 || true && \
    fc-cache -f -v

# تعیین متغیرهای محیطی برای کارکرد پاپتیر با کرومیوم نصب‌شده
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# تعیین دایرکتوری کاری
WORKDIR /app

# کپی فایل وابستگی‌ها و نصب پکیج‌ها
COPY package*.json ./
RUN npm install --production

# کپی بقیه فایل‌های پروژه
COPY . .

# باز کردن پورت برای Render
EXPOSE 3000

# فرمان شروع ربات
CMD ["node", "bot.js"]