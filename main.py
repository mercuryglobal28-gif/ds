import os
import json
import time
import re
import requests
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

app = Flask(__name__)

# ==============================================================================
# ⚙️ إعدادات البروكسي والثوابت
# ==============================================================================
PROXY_HOST = os.getenv("PROXY_HOST", "46.161.47.123")
PROXY_PORT = os.getenv("PROXY_PORT", "9771")
PROXY_USER = os.getenv("PROXY_USER", "oFRHax")
PROXY_PASS = os.getenv("PROXY_PASS", "4yFtU8")
BASE_URL = "https://kinovod120226.pro"

# استخراج الدومين لضبط الكوكيز
DOMAIN = BASE_URL.split("//")[-1]

REQUESTS_PROXY = {
    "http": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}",
    "https": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE_URL,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
}

# 🍪 الكوكيز السحري لإجبار الموقع على HLS
# القيمة: new|hls|0 (مشغل جديد | hls | بدون HDR)
FORCED_COOKIES = {
    "player_settings": "new|hls|0",
    "theme": "dark" # اختياري
}

# ==============================================================================
# 🛠️ أدوات مساعدة
# ==============================================================================
def parse_streams(file_string):
    """تحويل نص الروابط الطويل [360p]... إلى قاموس نظيف"""
    if not isinstance(file_string, str): return file_string
    
    streams = {}
    if "[" in file_string and "http" in file_string:
        parts = file_string.split(",")
        for part in parts:
            quality_match = re.search(r'\[(\d+p)\]', part)
            link_match = re.search(r'(https?://[^\s,\[\]]+)', part)
            
            if quality_match and link_match:
                quality = quality_match.group(1)
                link = link_match.group(1).split(" or ")[0]
                streams[quality] = link
        
        if streams: return streams
    return file_string

# ==============================================================================
# 🚀 المرحلة 1: البحث السريع (Requests)
# ==============================================================================
def fast_search(query_text):
    print(f"⚡ [Phase 1] البحث السريع: {query_text}...", flush=True)
    try:
        resp = requests.get(
            f"{BASE_URL}/search", 
            params={"query": query_text}, 
            headers=HEADERS, 
            proxies=REQUESTS_PROXY, 
            cookies=FORCED_COOKIES, # إرسال الكوكيز هنا أيضاً
            timeout=15
        )
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        item = soup.select_one(".items .item a")
        
        if item and item.get('href'):
            full_url = BASE_URL + item['href']
            print(f"✅ تم العثور على الرابط: {full_url}", flush=True)
            return full_url, None
            
        return None, "Not found"
    except Exception as e:
        print(f"⚠️ خطأ البحث السريع: {e}", flush=True)
        return None, str(e)

# ==============================================================================
# 🔎 المرحلة 2: استخراج مباشر من HTML (بدون متصفح)
# ==============================================================================
def extract_direct(target_url):
    print("⚡ [Phase 2] محاولة الاستخراج المباشر (Regex HTML)...", flush=True)
    try:
        # ⚠️ نرسل الكوكيز هنا لإجبار السيرفر على تجهيز روابط HLS في الكود
        resp = requests.get(target_url, headers=HEADERS, proxies=REQUESTS_PROXY, cookies=FORCED_COOKIES, timeout=15)
        html = resp.text

        # البحث عن نمط file:"..."
        file_match = re.search(r'file\s*:\s*["\']([^"\']+\.(?:mp4|m3u8)[^"\']*)["\']', html)
        if file_match:
            print("🎉 تم العثور على الرابط في HTML!", flush=True)
            return {"file": file_match.group(1), "source": "html_regex"}
            
        # البحث عن كائنات JSON في المتغيرات
        json_match = re.search(r'var (?:config|flashvars|playerConfig)\s*=\s*({.*?});', html)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if "file" in data:
                    print("🎉 تم العثور على JSON متغيرات في HTML!", flush=True)
                    return data
            except: pass
            
    except Exception as e:
        print(f"⚠️ فشل الاستخراج المباشر: {e}", flush=True)
    
    return None

# ==============================================================================
# 🐢 المرحلة 3: المتصفح (Playwright - الحل الشامل)
# ==============================================================================
def browser_scrape(target_url):
    print(f"🐢 [Phase 3] تشغيل المتصفح للرابط: {target_url}", flush=True)
    
    captured_data = None
    playwright = None
    browser = None
    
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            proxy={
                "server": f"http://{PROXY_HOST}:{PROXY_PORT}",
                "username": PROXY_USER,
                "password": PROXY_PASS
            },
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--no-zygote",
                "--single-process",
                "--blink-settings=imagesEnabled=false"
            ]
        )
        
        # إنشاء سياق وحقن الكوكيز فوراً
        context = browser.new_context(ignore_https_errors=True)
        
        # 🔥 حقن الكوكيز لإجبار HLS
        context.add_cookies([{
            "name": "player_settings",
            "value": "new|hls|0", # القيمة السحرية
            "domain": DOMAIN,
            "path": "/"
        }])
        
        page = context.new_page()
        page.set_default_timeout(60000)

        # ---------------------------------------------------------
        # المصيدة 1: اعتراض الردود (Response Listener) - للأفلام
        # ---------------------------------------------------------
        def handle_response(response):
            nonlocal captured_data
            if captured_data: return

            if response.status == 200 and ("/vod/" in response.url or "user_data" in response.url):
                try:
                    data = response.json()
                    if isinstance(data, dict) and ("file" in data or "playlist" in data):
                        print(f"🎥 تم التقاط بيانات الفيلم من: {response.url}", flush=True)
                        captured_data = data
                except: pass

        page.on("response", handle_response)

        # ---------------------------------------------------------
        # المصيدة 2: جاسوس الكونسول (Console Spy) - للمسلسلات
        # ---------------------------------------------------------
        page.add_init_script("""
            const originalParse = JSON.parse;
            JSON.parse = function(text, reviver) {
                try {
                    const result = originalParse(text, reviver);
                    const str = JSON.stringify(result);
                    // نبحث عن m3u8 بشكل خاص لأننا أجبرنا HLS
                    if ((str.includes('.m3u8') || str.includes('.mp4')) && (result.file || result.items || Array.isArray(result))) {
                        console.log('$$$JSON$$$' + str);
                    }
                    return result;
                } catch (e) { return originalParse(text, reviver); }
            }
        """)

        def handle_console(msg):
            nonlocal captured_data
            if captured_data: return
            if "$$$JSON$$$" in msg.text:
                try:
                    clean = msg.text.replace("$$$JSON$$$", "")
                    print("📦 تم التقاط بيانات المسلسل من الكونسول!", flush=True)
                    captured_data = json.loads(clean)
                except: pass

        page.on("console", handle_console)

        # ---------------------------------------------------------
        # تخفيف الشبكة
        # ---------------------------------------------------------
        page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,css}", lambda r: r.abort())
        
        # ---------------------------------------------------------
        # التنفيذ
        # ---------------------------------------------------------
        print("🚀 الدخول للصفحة...", flush=True)
        page.goto(target_url, wait_until="domcontentloaded")

        if "Just a moment" in page.title() or "403" in page.title():
            print("⛔ تم اكتشاف حماية Anti-Bot!", flush=True)
            return {"error": "Blocked"}

        # 🔥 محاولة النقر (للأفلام التي تتطلب Play)
        print("👆 البحث عن زر التشغيل...", flush=True)
        selectors = ["#videoplayer", ".player-poster", "#player", ".play-btn", ".play"]
        for sel in selectors:
            if captured_data: break
            try:
                if page.locator(sel).count() > 0:
                    page.click(sel, timeout=1000, force=True)
                    print(f"   ✓ تم النقر على: {sel}", flush=True)
                    break
            except: pass

        for i in range(15):
            if captured_data: break
            page.wait_for_timeout(1000)

    except Exception as e:
        print(f"⚠️ Playwright Error: {e}", flush=True)
    
    finally:
        if browser: browser.close()
        if playwright: playwright.stop()

    return captured_data

# ==============================================================================
# 🌐 API Routes
# ==============================================================================
@app.route('/')
def index():
    return jsonify({"status": "Active", "mode": "HLS Forced Scraper"})

@app.route('/scrape')
def scrape():
    query = request.args.get('query')
    if not query: return jsonify({"error": "Missing query"}), 400
    
    target_url, error = fast_search(query)
    if error: return jsonify({"error": error}), 404
    
    data = extract_direct(target_url)
    if data:
        if "file" in data: data["streams"] = parse_streams(data["file"])
        return jsonify(data)
    
    data = browser_scrape(target_url)
    if data:
        if "file" in data: data["streams"] = parse_streams(data["file"])
        return jsonify(data)

    return jsonify({"error": "Failed to capture data"}), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
