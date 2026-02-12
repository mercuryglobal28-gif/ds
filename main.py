from flask import Flask, jsonify
import json
import re
from playwright.sync_api import sync_playwright
import os

app = Flask(__name__)

# إعدادات الهدف
TARGET_URL = "https://kinovod120226.pro/serial/259509-predatelstvo"

def get_video_data_fast():
    print("🚀 بدء المعالجة على السيرفر...")
    video_data_container = []
    
    with sync_playwright() as p:
        # إعدادات المتصفح الخاصة بالسيرفر (مهمة جداً لـ Render)
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",           # ضروري لبيئة Render/Docker
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage" # لتجنب مشاكل الذاكرة
            ]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()

        # تسريع: حظر الموارد غير الضرورية
        page.route("**/*", lambda route: route.abort() 
                   if route.request.resource_type in ["image", "stylesheet", "font", "media", "ad"] 
                   else route.continue_())

        # المصيدة
        def handle_response(response):
            if "user_data" in response.url and response.status == 200:
                try:
                    text = response.text()
                    match = re.search(r'(\[.*\])', text, re.DOTALL)
                    if match:
                        print(f"🔥 تم صيد البيانات!")
                        data = json.loads(match.group(1))
                        video_data_container.append(data)
                except:
                    pass

        page.on("response", handle_response)

        try:
            # زيادة وقت الانتظار لأن السيرفرات المجانية قد تكون بطيئة
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            # انتظار البيانات
            for _ in range(50): # انتظار حتى 25 ثانية
                if len(video_data_container) > 0:
                    break
                page.wait_for_timeout(500)
                
        except Exception as e:
            print(f"❌ خطأ: {e}")

        browser.close()

    return video_data_container[0] if video_data_container else None

# نقطة النهاية API
@app.route('/')
def home():
    return "Running! Go to /get-json to fetch data."

@app.route('/get-json')
def fetch_data():
    data = get_video_data_fast()
    if data:
        return jsonify({
            "status": "success",
            "data": data
        })
    else:
        return jsonify({
            "status": "error",
            "message": "Failed to fetch data"
        }), 500

if __name__ == "__main__":
    # تشغيل محلي للتجربة
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))


