FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

# فونت‌های پشتیبان فارسی و ایموجی (📍)
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-core fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "bot.py"]
