import os
import json
import time
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

# ✅✅✅ هام جداً: هذا السطر يجب أن يكون هنا في البداية وغير داخل أي دالة
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
# 🛠️ دالة تشغيل المتصفح
# ==============================================================================
def get_browser():
    global playwright_instance, browser_instance
    
    if browser_instance and browser_instance.is_connected():
        return browser_instance

    print("🔄 تشغيل المتصفح...", flush=True)
    
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
        args=[
            "--no-sandbox", 
            "--disable-setuid-sandbox", 
            "--disable-dev-shm-usage",
            "--disable-gpu", 
            "--disable-extensions", 
            "--blink-settings=imagesEnabled=false",
            "--mute-audio"
        ]
    )
    return browser_instance

# ==============================================================================
# 🛡️ فلترة الشبكة
# ==============================================================================
def intercept_network(route, request):
    rt = request.resource_type
    if rt in ["image", "media", "font", "stylesheet", "other"]:
        return route.abort()
    if rt == "script":
        url = request.url.lower()
        if "kinovod" in url or "hs.js" in url or "jquery" in url:
            return route.continue_()
        return route.abort()
    return route.continue_()

# ==============================================================================
# 🔍🚀 المنطق الرئيسي
# ==============================================================================
def search_and_scrape(query_text):
    global browser_instance
    print(f"🔎 البحث عن: {query_text}", flush=True)
    
    captured_data = None
    context = None

    try:
        browser = get_browser()
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            ignore_https_errors=True
        )
        context.set_default_timeout(60000)
        
        page = context.new_page()
        page.route("**/*", intercept_network)

        # 1. البحث
        search_url = f"{BASE_URL}/search?query={query_text}"
        try: page.goto(search_url, wait_until="domcontentloaded")
        except: pass 

        try:
            page.wait_for_selector("a[href*='/serial/'], a[href*='/film/']", timeout=10000)
            element = page.query_selector("a[href*='/serial/'], a[href*='/film/']")
            
            if not element:
                return {"error": "Not found"}
            
            found_href = element.get_attribute("href")
            full_target_url = BASE_URL + found_href
            print(f"✅ تم العثور على الرابط: {full_target_url}", flush=True)

        except Exception as e:
            print(f"❌ خطأ في البحث: {e}", flush=True)
            return {"error": "Search failed"}

        # 2. الاستخراج
        spy_script = """
        const originalParse = JSON.parse;
        JSON.parse = function(text, reviver) {
            try {
                const result = originalParse(text, reviver);
                if (result) {
                    if (Array.isArray(result) || result.items || result.file || result.hls) {
                        console.log('$$$CAPTURED$$$' + JSON.stringify(result));
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
                clean_json = msg.text.replace("$$$CAPTURED$$$", "")
                try:
                    data = json.loads(clean_json)
                    if isinstance(data, list) or (isinstance(data, dict) and ("file" in data or "id" in data)):
                        captured_data = data
                except:
                    pass

        page.on("console", handle_console)
        print(f"🚀 الانتقال للصفحة...", flush=True)
        try: page.goto(full_target_url, wait_until="domcontentloaded", timeout=50000)
        except: pass

        for i in range(60):
            if captured_data: break
            page.wait_for_timeout(500)
            if i % 5 == 0:
                try: page.mouse.move(100, 100 + i)
                except: pass

    except Exception as e:
        print(f"⚠️ خطأ: {e}", flush=True)
        if "Target closed" in str(e) or "browser" in str(e).lower():
            browser_instance = None
        return {"error": str(e)}
    
    finally:
        if context: context.close()

    return captured_data

# ==============================================================================
# 🌐 المسارات
# ==============================================================================
@app.route('/')
def index():
    return jsonify({"status": "Running", "usage": "/scrape?query=Movie Name"})

@app.route('/scrape')
def scrape():
    query = request.args.get('query')
    if not query:
        return jsonify({"error": "Missing query param"}), 400
    
    data = search_and_scrape(query)
    
    if data and "error" not in data:
        return jsonify(data)
    return jsonify(data if data else {"error": "No data"}), 404

# ==============================================================================
# 🏁 التشغيل
# ==============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
