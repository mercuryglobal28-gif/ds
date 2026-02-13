from playwright.sync_api import sync_playwright
import json
import time
import os

# ==============================================================================
# ⚙️ الإعدادات (يمكنك تغييرها من واجهة Render عبر Environment Variables)
# ==============================================================================
PROXY_SERVER = os.getenv("PROXY_SERVER", "46.161.47.123:9771")
PROXY_USER = os.getenv("PROXY_USER", "oFRHax")
PROXY_PASS = os.getenv("PROXY_PASS", "4yFtU8")

TARGET_URL = "https://kinovod120226.pro/serial/259509-predatelstvo"

# ==============================================================================
# 🛡️ منطق الفلترة (لتحسين الأداء وتوفير الموارد)
# ==============================================================================
def intercept_network(route, request):
    url = request.url.lower()
    resource_type = request.resource_type

    # حظر الملفات غير الضرورية
    if any(x in url for x in ["hls.js", "favicon", ".ico", ".svg"]):
        return route.abort()

    if resource_type in ["image", "media", "font", "stylesheet"]:
        return route.abort()
    
    if resource_type == "script":
        # السماح بالملفات الأساسية فقط
        if "kinovod" in url or "hs.js" in url or "jquery" in url:
            return route.continue_()
        
        # حظر الإعلانات والتحليلات
        if any(x in url for x in ["google", "yandex", "facebook", "sentry", "ads"]):
            return route.abort()

        if "kinovod120226.pro" not in url:
            return route.abort()

    route.continue_()

# ==============================================================================
# 🚀 المشغل الرئيسي
# ==============================================================================
def run_scraper():
    print("🚀 بدء التشغيل على Render (الوضع المخفي)...")
    
    captured_data = None

    with sync_playwright() as p:
        # إطلاق المتصفح (إلزامي headless=True على Render)
        browser = p.chromium.launch(
            headless=True, 
            proxy={
                "server": f"http://{PROXY_SERVER}",
                "username": PROXY_USER,
                "password": PROXY_PASS
            },
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        page.route("**/*", intercept_network)

        # كود التجسس على JSON
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
                print("🎯 تم العثور على البيانات المطلوبة!")
                clean_json = msg.text.replace("$$$CAPTURED$$$", "")
                try:
                    captured_data = json.loads(clean_json)
                except Exception as e:
                    print(f"❌ خطأ في معالجة JSON: {e}")

        page.on("console", handle_console)

        try:
            print(f"🌍 جاري التوجه إلى: {TARGET_URL}")
            page.goto(TARGET_URL, timeout=60000, wait_until="domcontentloaded")
            
            # محاكاة تفاعل بسيط لضمان تشغيل السكربتات
            print("⏳ انتظار فك التشفير...")
            for i in range(15):
                if captured_data:
                    break
                page.wait_for_timeout(1000)
                page.mouse.wheel(0, 200) # تحريك الصفحة لأسفل قليلاً

        except Exception as e:
            print(f"⚠️ خطأ أثناء التشغيل: {e}")
        
        finally:
            browser.close()

    # المخرجات النهائية
    if captured_data:
        print("\n✅ النتيجة النهائية:")
        print(json.dumps(captured_data, indent=2, ensure_ascii=False))
        # ملاحظة: على Render، الملفات المحفوظة ستحذف عند إعادة التشغيل
        with open("result.json", "w", encoding="utf-8") as f:
            json.dump(captured_data, f, indent=4, ensure_ascii=False)
    else:
        print("❌ فشل التقاط البيانات. تأكد من إعدادات البروكسي.")

if __name__ == "__main__":
    run_scraper()
