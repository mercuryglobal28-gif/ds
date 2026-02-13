import os
import json
from flask import Flask, jsonify
from playwright.sync_api import sync_playwright

# إعداد تطبيق Flask
app = Flask(__name__)

# ==============================================================================
# ⚙️ الإعدادات
# ==============================================================================
PROXY_SERVER = os.getenv("PROXY_SERVER", "46.161.47.123:9771")
PROXY_USER = os.getenv("PROXY_USER", "oFRHax")
PROXY_PASS = os.getenv("PROXY_PASS", "4yFtU8")

TARGET_URL = "https://kinovod120226.pro/serial/259509-predatelstvo"

# ==============================================================================
# 🛡️ منطق الفلترة (كما هو)
# ==============================================================================
def intercept_network(route, request):
    url = request.url.lower()
    resource_type = request.resource_type

    if any(x in url for x in ["hls.js", "favicon", ".ico", ".svg"]):
        return route.abort()

    if resource_type in ["image", "media", "font", "stylesheet"]:
        return route.abort()
    
    if resource_type == "script":
        if "kinovod" in url or "hs.js" in url or "jquery" in url:
            return route.continue_()
        
        if any(x in url for x in ["google", "yandex", "facebook", "sentry", "mc.yandex", "ads"]):
            return route.abort()

        if "kinovod120226.pro" not in url:
            return route.abort()

    route.continue_()

# ==============================================================================
# 🚀 دالة الجاسوس (تُستدعى عند الطلب)
# ==============================================================================
def scrape_logic():
    print("🚀 بدء عملية الاستخراج...", flush=True)
    captured_data = None

    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(
                headless=True,
                proxy={
                    "server": f"http://{PROXY_SERVER}",
                    "username": PROXY_USER,
                    "password": PROXY_PASS
                },
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage",
                    "--disable-gpu", 
                    "--blink-settings=imagesEnabled=false"
                ]
            )
            
            page = browser.new_page()
            page.route("**/*", intercept_network)

            spy_script = """
            const originalParse = JSON.parse;
            JSON.parse = function(text, reviver) {
                const result = originalParse(text, reviver);
                if (result && (Array.isArray(result) || result.items)) {
                    console.log('$$$CAPTURED$$$' + JSON.stringify(result));
                }
                return result;
            }
            """
            page.add_init_script(spy_script)

            def handle_console(msg):
                nonlocal captured_data
                if "$$$CAPTURED$$$" in msg.text:
                    clean_json = msg.text.replace("$$$CAPTURED$$$", "")
                    try:
                        captured_data = json.loads(clean_json)
                    except:
                        pass

            page.on("console", handle_console)

            print(f"🌍 تحميل الصفحة: {TARGET_URL}", flush=True)
            page.goto(TARGET_URL, timeout=60000, wait_until="commit")
            
            # الانتظار حتى يتم التقاط البيانات
            for i in range(30):
                if captured_data:
                    break
                page.wait_for_timeout(1000)
                try:
                    page.mouse.move(100, i*10)
                except:
                    pass

        except Exception as e:
            print(f"⚠️ خطأ: {e}", flush=True)
            return {"error": str(e)}
        
        finally:
            if browser:
                browser.close()

    return captured_data

# ==============================================================================
# 🌐 مسار الويب (الرابط الرئيسي)
# ==============================================================================
@app.route('/')
def index():
    data = scrape_logic()
    if data:
        return jsonify(data)
    else:
        return jsonify({"status": "failed", "message": "No data captured"}), 500

# تشغيل السيرفر (مهم لـ Render)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
