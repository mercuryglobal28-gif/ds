# استخدام صورة رسمية من Playwright تحتوي على المتطلبات
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# نسخ ملف المتطلبات وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# تثبيت المتصفح
RUN playwright install chromium

# نسخ باقي الملفات
COPY . .

# أمر التشغيل (يستخدم المنفذ الذي يوفره Render)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]