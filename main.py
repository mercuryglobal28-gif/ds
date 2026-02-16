import os
import json
import time
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# ==============================================================================
# ⚙️ الإعدادات
# ==============================================================================
PROXY_SERVER = os.getenv("PROXY_SERVER", "46.161.47.123:9771")
PROXY_USER = os.getenv("PROXY_USER", "oFRHax")
PROXY_PASS = os.getenv("PROXY_PASS", "4yFtU8")
BASE_URL = "https://kinovod120226.pro"

playwright_instance = None
browser_instance = None

# ==============================================================================
# 🛠️ تشغيل المتصفح
# ==============================================================================
def get_browser():
    global playwright_instance, browser_instance
    if browser_instance and browser_instance.is_connected():
        return browser_instance

    if playwright_instance:
        try: playwright_instance.stop()
        except: pass

    playwright_instance = sync_playwright().start()
    browser_instance = playwright_instance.chromium.launch(
        headless=True,
        proxy={
            "server": f"http://{PROXY_SERVER}",
            "username": PROXY_USER,
            "password": PROXY_PASS
        },
        args=["--no-sandbox", "--disable-gpu", "--blink-settings=imagesEnabled=false"]
    )
    return browser_instance

# ==============================================================================
# 🛡️ فلترة الشبكة
# ==============================================================================
def intercept_network(route, request):
    rt = request.resource_type
    if rt in ["image", "font", "stylesheet", "other"]:
        return route.abort()
    if rt == "script":
        url = request.url.lower()
        if any(x in url for x in ["kinovod", "hs.js", "jquery", "player", "bundle"]):
            return route.continue_()
        return route.abort()
    return route.continue_()

# ==============================================================================
# 🔍🚀 المنطق الرئيسي (المنقّح)
# ==============================================================================
def search_and_scrape(query_text):
    global browser_instance
    print(f"🔎 البحث عن: {query_text}", flush=True)
    
    captured_data = None
    context = None

    try:
        browser = get_browser()
        context = browser.new_context(ignore_https_errors=True)
        context.set_default_timeout(60000)
        
        page = context.new_page()
        page.route("**/*", intercept_network)

        # 1. البحث
        try:
            page.goto(f"{BASE_URL}/search?query={query_text}", wait_until="domcontentloaded")
            page.wait_for_selector("a[href*='/serial/'], a[href*='/film/']", timeout=10000)
            element = page.query_selector("a[href*='/serial/'], a[href*='/film/']")
            
            if not element: return {"error": "Not found"}
            
            target_url = BASE_URL + element.get_attribute("href")
            print(f"✅ الرابط: {target_url}", flush=True)
            
        except Exception as e:
            return {"error": f"Search failed: {e}"}

        # 2. حقن الجاسوس (محسّن جداً)
        spy_script = """
        const originalParse = JSON.parse;
        JSON.parse = function(text, reviver) {
            try {
                const result = originalParse(text, reviver);
                const str = JSON.stringify(result);
                
                // التقاط المسلسلات (مصفوفة) أو الأفلام (إذا كان يحتوي على ملف MP4)
                if (str.includes('.mp4') || str.includes('.m3u8')) {
                    if (Array.isArray(result) || result.file || (result.items && result.items.length > 0)) {
                         console.log('$$$CAPTURED$$$' + str);
                    }
                }
                return result;
            } catch (e) { return originalParse(text, reviver); }
        }
        """
        page.add_init_script(spy_script)

        def handle_console(msg):
            nonlocal captured_data
            if "$$$CAPTURED$$$" in msg.text:
                clean = msg.text.replace("$$$CAPTURED$$$", "")
                try: captured_data = json.loads(clean)
                except: pass

        page.on("console", handle_console)
        
        print("🚀 الدخول للصفحة...", flush=True)
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

        # 3. محاولة الالتقاط (تلقائي + يدوي)
        for i in range(20): # 10 ثواني (20 * 0.5)
            if captured_data: break
            
            # محاولة استخراج يدوية للأفلام (Plan B)
            # نفحص المتغيرات العامة في الصفحة التي قد تحتوي الرابط
            if i % 4 == 0: # كل ثانيتين
                try:
                    # نحاول قراءة متغيرات مشهورة يستخدمها المشغل
                    manual_data = page.evaluate("""() => {
                        // البحث عن أي متغير يحتوي على رابط mp4
                        if (window.flashvars && window.flashvars.file) return {file: window.flashvars.file};
                        if (window.config && window.config.file) return {file: window.config.file};
                        if (window.pl && window.pl.file) return {file: window.pl.file};
                        return null;
                    }""")
                    if manual_data:
                        captured_data = manual_data
                        break
                except: pass

            page.mouse.move(100, 100 + i*10)
            page.wait_for_timeout(500)

    except Exception as e:
        print(f"⚠️ خطأ: {e}", flush=True)
        if "Target closed" in str(e): browser_instance = None
        return {"error": str(e)}
    
    finally:
        if context: context.close()

    return captured_data

# ==============================================================================
# 🌐 Routes
# ==============================================================================
@app.route('/')
def index(): return jsonify({"status": "Running"})

@app.route('/scrape')
def scrape():
    query = request.args.get('query')
    if not query: return jsonify({"error": "Missing query"}), 400
    
    data = search_and_scrape(query)
    
    if data and "error" not in data: return jsonify(data)
    return jsonify(data if data else {"error": "No data captured"}), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
