import os
import json
import time
import re
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
# 🛡️ فلترة الشبكة (لمنع تحميل الصور والإعلانات)
# ==============================================================================
def intercept_network(route, request):
    rt = request.resource_type
    if rt in ["image", "font", "stylesheet", "media"]: # منع تحميل الميديا لتسريع العمل
        return route.abort()
    
    # السماح فقط بالنطاقات والسكربتات المهمة
    url = request.url.lower()
    if rt == "script":
        if any(x in url for x in ["kinovod", "hs.js", "jquery", "player", "bundle", "hls"]):
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
        context = browser.new_context(ignore_https_errors=True)
        context.set_default_timeout(60000)
        
        page = context.new_page()

        # ==================================================================
        # 🔥 الحل السحري: اعتراض الردود (Response Listener)
        # ==================================================================
        def handle_response(response):
            nonlocal captured_data
            url = response.url
            
            # نحن نبحث عن رابط يحتوي على /vod/ (للأفلام والمسلسلات)
            if "/vod/" in url and response.status == 200:
                try:
                    # محاولة قراءة الرد كـ JSON
                    json_body = response.json()
                    
                    # التحقق من وجود الحقل 'file' كما في البيانات التي أرسلتها
                    if isinstance(json_body, dict) and "file" in json_body:
                        print(f"✅ تم اصطياد JSON من الرابط: {url}", flush=True)
                        captured_data = json_body
                        
                except Exception as e:
                    # قد يكون الرد ليس JSON، نتجاهله
                    pass

        # تفعيل المستمع
        page.on("response", handle_response)
        page.route("**/*", intercept_network)

        # 1. البحث والوصول لصفحة الفيلم
        try:
            page.goto(f"{BASE_URL}/search?query={query_text}", wait_until="domcontentloaded")
            page.wait_for_selector(".items .item a", timeout=15000) 
            
            element = page.query_selector(".items .item a")
            if not element: return {"error": "Not found"}
            
            href = element.get_attribute("href")
            target_url = BASE_URL + href
            print(f"🔗 رابط الصفحة: {target_url}", flush=True)
            
        except Exception as e:
            return {"error": f"Search failed: {e}"}

        # 2. الدخول للصفحة وانتظار الطلب
        # (لا نحتاج لحقن JS لأننا نراقب الشبكة مباشرة الآن)
        print("🚀 الدخول للصفحة...", flush=True)
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

        # 3. حلقة الانتظار (Wait Loop)
        for i in range(20): # 10 ثواني تقريباً
            if captured_data: 
                print("📦 البيانات جاهزة!", flush=True)
                break
            
            # تحريك الماوس لتحفيز تحميل المشغل إذا لزم الأمر
            try: page.mouse.move(100, 100 + i*10)
            except: pass
            
            page.wait_for_timeout(500)

        # 4. تنظيف ومعالجة البيانات قبل الإرجاع
        if captured_data and "file" in captured_data:
            file_string = captured_data["file"]
            
            # تحسين: تحويل النص الطويل إلى قائمة روابط نظيفة
            # المثال: "[360p]url... ,[720p]url..."
            streams = {}
            if "[" in file_string:
                # تقسيم بناءً على الفاصلة التي تسبق الأقواس (أو الفواصل العادية)
                parts = file_string.split(",")
                for part in parts:
                    quality_match = re.search(r'\[(\d+p)\]', part)
                    link_match = re.search(r'(https?://[^\s,]+)', part)
                    
                    if quality_match and link_match:
                        quality = quality_match.group(1)
                        link = link_match.group(1)
                        # تنظيف الرابط من " or https..."
                        if " or " in link:
                            link = link.split(" or ")[0]
                        streams[quality] = link
            
            # إضافة الروابط المنظمة للرد
            if streams:
                captured_data["streams"] = streams

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
