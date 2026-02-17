# استخدام صورة بايثون خفيفة
FROM python:3.10-slim

# إعداد متغيرات البيئة
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# 1. نسخ ملف المتطلبات وتثبيت المكتبات
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 2. 🔥 الخطوة الحاسمة: تثبيت متصفحات Playwright وتوابعها
# هذا الأمر سيجبر النظام على تحميل نسخة كروم المتوافقة مع نسخة المكتبة (1.58.0)
RUN playwright install --with-deps chromium

# 3. نسخ باقي ملفات المشروع
COPY . .

# 4. فتح المنفذ
EXPOSE 10000

# 5. تشغيل التطبيق
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:10000", "main:app"]
