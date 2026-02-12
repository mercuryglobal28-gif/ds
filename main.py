from flask import Flask, jsonify
import json
import re
from playwright.sync_api import sync_playwright
import os
import subprocess

# تثبيت المتصفح عند البدء (Firefox أخف)
def install_playwright():
    print("🛠️ Checking Playwright (Firefox)...")
    try:
        subprocess.run(["playwright", "install", "firefox"])
    except Exception as e:
        print(f"⚠️ Install error: {e}")

install_playwright()

app = Flask(__name__)
TARGET_URL = "https://kinovod120226.pro/serial/259509-predatelstvo"

def get_video_data_lightweight():
    print("🚀 بدء المعالجة (وضع توفير الذاكرة)...")
    video_data = None
    
    with sync_playwright() as p:
        # استخدام Firefox لأنه يستهلك ذاكرة أقل من Chrome
        browser = p.firefox.launch(
            headless=True,
            args=["--no-remote"] # تقليل العمليات الخلفية
        )
        
        # سياق صفحة واحد فقط بدون تخزين
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
            java_script_enabled=True, # نحتاج JS ليعمل hs.js
            bypass_csp=True,
            viewport={"width": 800, "height": 600} # شاشة صغيرة لتقليل الذاكرة
        )
        
        page = context.new_page()

        # حظر صارم للموارد
        page.route("**/*", lambda route: route.abort() 
                   if route.request.resource_type in ["image", "stylesheet", "font", "media", "other"] 
                   else route.continue_())

        def handle_response(response):
            nonlocal video_data
            if "user_data" in response.url and response.status == 200:
                try:
                    text = response.text()
                    match = re.search(r'(\[.*\])', text, re.DOTALL)
                    if match:
                        print(f"🔥 تم الصيد!")
                        video_data = json.loads(match.group(1))
                except:
                    pass

        page.on("response", handle_response)

        try:
            # مهلة قصيرة لتقليل الانتظار
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=45000)
            
            # انتظار ذكي
            for _ in range(30):
                if video_data: break
                page.wait_for_timeout(500)
                
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            # تنظيف الذاكرة فوراً
            context.close()
            browser.close()

    return video_data

@app.route('/')
def home():
    return "Lite Scraper Running"

@app.route('/get-json')
def fetch_data():
    try:
        data = get_video_data_lightweight()
        if data:
            return jsonify({"status": "success", "data": data})
        return jsonify({"status": "error", "message": "No data found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
