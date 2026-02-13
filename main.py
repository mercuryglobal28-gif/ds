import os
import json
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

# متغيرات للاحتفاظ بالمتصفح مفتوحاً (للسرعة)
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
            "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
            "--disable-gpu", "--disable-extensions", "--blink-settings=imagesEnabled=false",
            "--mute-audio"
        ]
    )
    return browser_instance

# ==============================================================================
# 🛡️ فلترة الشبكة
# ==============================================================================
def intercept_network(route, request):
    rt = request.resource_type
    # حظر الموارد الثقيلة
    if rt in ["image", "media", "font", "stylesheet", "other"]:
        return route.abort()
    if rt == "script":
        url = request.url.lower()
        # السماح فقط للسكربتات الضرورية
        if "kinovod" in url or "hs.js" in url or "jquery" in url:
            return route.continue_()
        return route.abort()
    
    return route.continue_()

# ==============================================================================
# 🔍🚀 المنطق الرئيسي: بحث + استخراج
# ==============================================================================
def search_and_scrape(query_text):
    global browser_instance
    print(f"🔎 البحث عن: {query_text}", flush=True)
    
    captured_data = None
    context = None

    try:
        browser = get_browser()
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        context.set_default_timeout(45000)
        page = context.new_page()
        page.route("**/*", intercept_network)

        # ---------------------------------------------------------
        # 1️⃣ المرحلة الأولى: البحث
        # ---------------------------------------------------------
        search_url = f"{BASE_URL}/search?query={query_text}"
        try:
            page.goto(search_url, wait_until="domcontentloaded")
        except:
            pass # قد يكون هناك timeout لكن المحتوى وصل

        # البحث عن أول رابط يحتوي على /serial/ أو /film/ في النتائج
        # نستخدم selector يبحث عن وسم <a> يحتوي الـ href الخاص به على الكلمة
        try:
            # ننتظر قليلاً لظهور النتائج
            page.wait_for_selector("a[href*='/serial/'], a[href*='/film/']", timeout=5000)
            
            # جلب الرابط
            element = page.query_selector("a[href*='/serial/'], a[href*='/film/']")
            
            if not element:
                print("❌ لم يتم العثور على نتائج بحث.", flush=True)
                return {"error": "Not found", "query": query_text}
            
            found_href = element.get_attribute("href")
            full_target_url = BASE_URL + found_href
            print(f"✅ تم العثور على الرابط: {full_target_url}", flush=True)

        except Exception as e:
            print(f"❌ خطأ أثناء البحث في HTML: {e}", flush=True)
            return {"error": "Search failed or no results"}

        # ---------------------------------------------------------
        # 2️⃣ المرحلة الثانية: الاستخراج (Spy)
        # ---------------------------------------------------------
        
        # حقن كود الجاسوس قبل الانتقال
        spy_script = """
        const originalParse = JSON.parse;
        JSON.parse = function(text, reviver) {
            try {
                const result = originalParse(text, reviver);
                if (result && (Array.isArray(result) || result.items)) {
                    console.log('$$$CAPTURED$$$' + JSON.stringify(result));
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
                    captured_data = json.loads(clean_json)
                except:
                    pass

        page.on("console", handle_console)

        print(f"🚀 الانتقال لصفحة الفيلم...", flush=True)
        try:
            page.goto(full_target_url, wait_until="domcontentloaded", timeout=40000)
        except:
            pass

        # انتظار البيانات
        for i in range(50):
            if captured_data:
                break
            page.wait_for_timeout(400)

    except Exception as e:
        print(f"⚠️ خطأ حرج: {e}", flush=True)
        if "Target closed" in str(e) or "browser" in str(e).lower():
            browser_instance = None
        return {"error": str(e)}
    
    finally:
        if context:
            context.close()

    return captured_data

# ==============================================================================
# 🌐 المسارات
# ==============================================================================
@app.route('/')
def index():
    return jsonify({
        "status": "Running",
        "usage": "/scrape?query=Your Movie Name"
    })

@app.route('/scrape')
def scrape():
    # استقبال المتغير query من الرابط
    query = request.args.get('query')
    
    if not query:
        return jsonify({"error": "Please provide a query param. Example: /scrape?query=Matrix"}), 400

    data = search_and_scrape(query)
    
    if data and "error" not in data:
        return jsonify(data)
    elif data and "error" in data:
        return jsonify(data), 404
    else:
        return jsonify({"status": "failed", "message": "No data captured"}), 500

if __name__ == "__main__":
    try: get_browser()
    except: pass
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
