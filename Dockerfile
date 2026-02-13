# استخدام صورة Playwright الرسمية (تتضمن بايثون والمتصفحات)
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# إعداد مجلد العمل
WORKDIR /app

# نسخ ملف المتطلبات وتثبيته
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# أمر التشغيل
CMD ["python", "main.py"]
