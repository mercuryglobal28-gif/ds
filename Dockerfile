FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# السماح بمنفذ الشبكة (اختياري لكن مفيد للتوثيق)
EXPOSE 10000

# أمر التشغيل باستخدام Gunicorn ليكون سيرفر ويب حقيقي
CMD ["gunicorn", "-b", "0.0.0.0:10000", "--timeout", "120", "main:app"]
