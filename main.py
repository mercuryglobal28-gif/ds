import os
import json
import time
import re
import requests
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup  # ⚠️ تأكد من تثبيت: pip install beautifulsoup4 requests

app = Flask(__name__)

# ==============================================================================
# ⚙️ الإعدادات والثوابت
# ==============================================================================
PROXY_HOST = os.getenv("PROXY_HOST", "46.161.47.123")
PROXY_PORT = os.getenv("PROXY_PORT", "9771")
PROXY_USER = os.getenv("PROXY_USER", "oFRHax")
PROXY_PASS = os.getenv("PROXY_PASS", "4yFtU8")
BASE_URL = "https://kinovod120226.pro"

# إعداد البروكسي لمكتبة Requests
REQUESTS_PROXY = {
    "http": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}",
    "https": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}",
}

# هيدرز لتبدو كمتصفح حقيقي (مهم جداً لتجنب الحظر)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Referer": BASE_URL
}

# ==============================================================================
# 🚀 المرحلة الأولى: البحث السريع (بدون متصفح)
# ==============================================================================
def fast_search(query_text):
    print(f"⚡ [Phase 1] جاري البحث السريع عن: {query_text}...", flush=True)
    try:
        search_url = f"{BASE_URL}/search"
        params = {"query": query_text}
        
        # طلب HTML مباشرة
        resp = requests.get(
            search_url, 
            params=params, 
            headers=HEADERS, 
            proxies=REQUESTS_PROXY, 
            timeout=15
        )
        
        if resp.status_code != 200:
            return None, f"HTTP Error: {resp.status_code}"

        # تحليل HTML
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # البحث عن أول نتيجة في القائمة (.items .item a)
        first_item = soup.select_one(".items .item a")
        
        if first_item and first_item.get('href'):
            full_url = BASE_URL + first_item['href']
            print(f"✅ تم العثور على الرابط: {full_url}", flush=True)
            return full_url, None
        
        return None, "Not found"

    except Exception as e:
        print(f"⚠️ خطأ في البحث السريع: {e}", flush=True)
        return None, str(e)

# ==============================================================================
# 🖥️ المرحلة الثانية: فتح المتصفح والاستخراج
# ==============================================================================
def browser_scrape(target_url):
    print(f"🐢 [Phase 2] تشغيل المتصفح للرابط: {target_url}", flush=True)
    
    captured_data = None
    playwright = None
    browser = None
    context = None

    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            proxy={
                "server": f"http://{PROXY_HOST}:{PROXY_PORT}",
                "username": PROXY_USER,
                "password": PROXY_PASS
            },
            args=["--no-sandbox", "--disable-gpu", "--blink-settings=imagesEnabled=false"]
        )
        
        context = browser.new_context(ignore_https_errors=True)
        context.set_default_timeout(60000)
        page = context.new_page()

        # -------------------------------------------------
        # 1. اعتراض الردود (للأفلام) - Network Response
        # -------------------------------------------------
        def handle_response(response):
            nonlocal captured_data
            if captured_data: return
            
            if "/vod/" in response.url and response.status == 200:
                try:
                    data = response.json()
                    if isinstance(data, dict) and "file" in data:
                        print("🎥 تم التقاط JSON الفيلم من الشبكة!", flush=True)
                        captured_data = data
                except: pass

        page.on("response", handle_response)

        # -------------------------------------------------
        # 2. حقن جاسوس الكونسول (للمسلسلات) - Console Spy
        # -------------------------------------------------
        spy_script = """
        const originalParse = JSON.parse;
        JSON.parse = function(text, reviver) {
            try {
                const result = originalParse(text, reviver);
                if (result && typeof result === 'object') {
                    const str = JSON.stringify(result);
                    if ((str.includes('.mp4') || str.includes('.m3u8')) && (result.file || result.items)) {
                         console.log('$$$JSON$$$' + str);
                    }
                }
                return result;
            } catch (e) { return originalParse(text, reviver); }
        }
        """
        page.add_init_script(spy_script)

        def handle_console(msg):
            nonlocal captured_data
            if captured_data: return
            if "$$$JSON$$$" in msg.text:
                try:
                    clean = msg.text.replace("$$$JSON$$$", "")
                    data = json.loads(clean)
                    print("📦 تم التقاط JSON المسلسل من الكونسول!", flush=True)
                    captured_data = data
                except: pass

        page.on("console", handle_console)

        # -------------------------------------------------
        # 3. تخفيف الشبكة (Blocking Assets)
        # -------------------------------------------------
        def intercept_route(route):
            if route.request.resource_type in ["image", "font", "stylesheet", "media"]:
                return route.abort()
            return route.continue_()
        
        page.route("**/*", intercept_route)

        # -------------------------------------------------
        # 4. التنفيذ
        # -------------------------------------------------
        print("🚀 الدخول للصفحة...", flush=True)
        page.goto(target_url, wait_until="domcontentloaded")

        # حلقة الانتظار (Wait Loop)
        for i in range(20): # 10 ثواني
            if captured_data: break
            
            # محاولة البحث اليدوي في المتغيرات (Backup)
            if i > 5 and not captured_data:
                try:
                    manual = page.evaluate("() => window.flashvars || window.config || null")
                    if manual and manual.get('file'):
                        print("⚡ تم العثور على البيانات في Window Object", flush=True)
                        captured_data = manual
                        break
                except: pass

            try: page.mouse.move(100, 100 + i*10)
            except: pass
            
            page.wait_for_timeout(500)

    except Exception as e:
        print(f"⚠️ Playwright Error: {e}", flush=True)
        return {"error": str(e)}
    
    finally:
        if context: context.close()
        if browser: browser.close()
        if playwright: playwright.stop()

    # معالجة البيانات النهائية
    if captured_data and "file" in captured_data:
        # تنظيف الروابط إذا كانت نصاً واحداً طويلاً
        file_str = captured_data["file"]
        if isinstance(file_str, str) and "[" in file_str:
            streams = {}
            parts = file_str.split(",")
            for part in parts:
                q = re.search(r'\[(\d+p)\]', part)
                l = re.search(r'(https?://[^\s,]+)', part)
                if q and l:
                    streams[q.group(1)] = l.group(1).split(" or ")[0]
            if streams: captured_data["streams"] = streams

    return captured_data

# ==============================================================================
# 🌐 API Routes
# ==============================================================================
@app.route('/scrape')
def scrape():
    query = request.args.get('query')
    if not query: return jsonify({"error": "Missing query"}), 400
    
    # 1. المرحلة الأولى: البحث السريع
    target_url, error = fast_search(query)
    
    if error:
        return jsonify({"error": error}), 404
    
    if not target_url:
        return jsonify({"error": "Result not found"}), 404

    # 2. المرحلة الثانية: المتصفح
    data = browser_scrape(target_url)
    
    if data: return jsonify(data)
    return jsonify({"error": "No data captured from browser"}), 404

if __name__ == "__main__":
    # تثبيت المكتبات المطلوبة أولاً إذا لم تكن موجودة
    # pip install beautifulsoup4 requests playwright flask
    # playwright install chromium
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
