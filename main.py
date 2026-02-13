import os
import json
import time
from playwright.sync_api import sync_playwright

# ==============================================================================
# ⚙️ الإعدادات (قراءة من متغيرات البيئة للأمان)
# ==============================================================================
# إذا لم تجد المتغيرات، ستستخدم القيم الافتراضية الموجودة هنا
PROXY_SERVER = os.getenv("PROXY_SERVER", "46.161.47.123:9771")
PROXY_USER = os.getenv("PROXY_USER", "oFRHax")
PROXY_PASS = os.getenv("PROXY_PASS", "4yFtU8")

TARGET_URL = "https://kinovod120226.pro/serial/259509-predatelstvo"

# ==============================================================================
# 🛡️ منطق الفلترة
# ==============================================================================
def intercept_network(route, request):
    url = request.url.lower()
    resource_type = request.resource_type

    # تحسين السرعة
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
# 🚀 المشغل الرئيسي
# ==============================================================================
def run_optimized_spy_blocked_master():
    print("🚀 تشغيل الجاسوس الذكي على Render...", flush=True)
    
    captured_data = None

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=True, # يجب أن يكون True في السيرفرات
                proxy={
                    "server": f"http://{PROXY_SERVER}",
                    "username": PROXY_USER,
                    "password": PROXY_PASS
                },
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage", # مهم جداً لـ Docker
                    "--disable-gpu", 
                    "--blink-settings=imagesEnabled=false"
                ]
            )
            
            page = browser.new_page()
            page.route("**/*", intercept_network)

            # حقن كود اعتراض JSON
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
                    print("🎯 تم التقاط البيانات المفكوكة!", flush=True)
                    clean_json = msg.text.replace("$$$CAPTURED$$$", "")
                    try:
                        captured_data = json.loads(clean_json)
                    except:
                        pass

            page.on("console", handle_console)

            print(f"🌍 جاري التحميل: {TARGET_URL}", flush=True)
            page.goto(TARGET_URL, timeout=60000, wait_until="commit")
            
            print("⏳ انتظار البيانات...", flush=True)
            for i in range(30):
                if captured_data:
                    break
                page.wait_for_timeout(1000)
                # محاكاة حركة ماوس بسيطة
                try:
                    page.mouse.move(100, i*10)
                except:
                    pass

        except Exception as e:
            print(f"⚠️ خطأ أثناء التشغيل: {e}", flush=True)
        
        finally:
            if 'browser' in locals():
                browser.close()

    if captured_data:
        print("\n" + "="*50)
        print("🎉 البيانات النهائية:")
        # طباعة JSON في الـ Logs لتتمكن من رؤيتها في Render Dashboard
        print(json.dumps(captured_data, indent=4, ensure_ascii=False), flush=True)
    else:
        print("❌ لم يتم التقاط البيانات.", flush=True)

if __name__ == "__main__":
    run_optimized_spy_blocked_master()
