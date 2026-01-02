from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback
import base64
from urllib.parse import unquote

app = FastAPI()

# ==============================================================================
# 💎 إعدادات البروكسي المدفوع
# ==============================================================================
WORKING_PROXY = "http://40jSHv:RcQr6u@147.45.56.91:8000"
# ==============================================================================

def scrape_movie_data(full_url: str, debug_logs: list):
    logs = debug_logs
    logs.append(f"🚀 Start: Connecting via Private Proxy...")
    
    movie_data = None
    snapshot = ""
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=True,
                proxy={"server": WORKING_PROXY},
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage" # تقليل استهلاك الذاكرة
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", 
                timezone_id="Europe/Moscow",
                ignore_https_errors=True # تجاهل أخطاء الشهادات لتسريع الاتصال
            )
            
            # مهلة 60 ثانية كافية جداً
            context.set_default_timeout(60000) 
            page = context.new_page()

            # 1. خطوة فحص البروكسي (Sanity Check)
            try:
                logs.append("🕵️ Checking Proxy IP...")
                # موقع خفيف جداً للتأكد من الاتصال
                page.goto("http://checkip.amazonaws.com", timeout=10000)
                ip = page.content().strip()
                logs.append(f"✅ Proxy Works! IP: {ip[:20]}...")
            except Exception as e:
                logs.append(f"⚠️ Proxy Check Warning: {str(e)}")

            # 2. إعداد المصيدة
            def handle_response(response):
                nonlocal movie_data
                try:
                    if response.status == 200:
                        # التقاط ملفات البيانات
                        if ("bnsi/movies" in response.url or "cdn/movie" in response.url):
                            data = response.json()
                            if "hlsSource" in data or "file" in data:
                                movie_data = data
                                logs.append("✅ JSON Data Captured!")
                        
                        # التقاط ملفات التشغيل المباشرة
                        if "m3u8" in response.url and "master" in response.url:
                             if not movie_data:
                                 movie_data = {"direct_m3u8": response.url}
                                 logs.append("✅ Direct M3U8 Found")
                except: pass

            page.on("response", handle_response)

            # 3. تسريع الصفحة بحظر الموارد غير الضرورية
            def intercept_route(route):
                # نحظر الصور والخطوط فقط، ونسمح بالباقي
                if route.request.resource_type in ["image", "font", "stylesheet"]:
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", intercept_route)

            # 4. الذهاب للموقع (الاستراتيجية السريعة)
            try:
                logs.append(f"⏳ Navigating to Movie URL...")
                # wait_until="commit": لا ننتظر تحميل الصفحة، ننتظر فقط بدء الاتصال
                page.goto(full_url, wait_until="commit", timeout=45000)
                logs.append("✅ Connection established, waiting for scripts...")

                # ننتظر 15 ثانية فقط لتقوم السكربتات بطلب الفيديو في الخلفية
                for _ in range(150):
                    if movie_data: 
                        logs.append("🎯 Data caught early!")
                        break
                    
                    # محاولة نقر وهمية لتنشيط المشغل
                    if _ % 20 == 0: # كل ثانيتين
                        try:
                            page.wait_for_selector("iframe", timeout=1000)
                            page.mouse.click(500, 300)
                        except: pass
                        
                    page.wait_for_timeout(100)

            except Exception as e:
                logs.append(f"⚠️ Navigation Timeout (Expected): {str(e)}")

            # التقاط صورة فقط إذا فشلنا تماماً
            if not movie_data:
                try:
                    screenshot_bytes = page.screenshot(type='jpeg', quality=30)
                    snapshot = base64.b64encode(screenshot_bytes).decode('utf-8')
                    logs.append("📸 Screenshot captured")
                except: pass

            browser.close()
            
            if movie_data:
                return movie_data
            else:
                return {
                    "success": False, 
                    "error": "No Data Found", 
                    "logs": logs,
                    "screenshot_base64": snapshot
                }

        except Exception as e:
            return {"success": False, "error": f"Critical Error: {str(e)}", "trace": traceback.format_exc()}

# ==============================================================================
# الواجهة والكود المساعد
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head><title>Pro Scraper</title></head>
        <body style="font-family:sans-serif; text-align:center; padding:50px;">
            <h1>🚀 Pro Proxy Scraper</h1>
            <p>Paste the full URL below:</p>
            <input type="text" id="url" style="width:80%; padding:10px;" placeholder="https://mercuryglobal...&token=...">
            <br><br>
            <button onclick="go()" style="padding:10px 20px; background:blue; color:white; cursor:pointer;">Get Data</button>
            <div id="log" style="text-align:left; background:#eee; padding:20px; margin-top:20px; white-space:pre-wrap;"></div>
            <script>
                async function go() {
                    const u = document.getElementById('url').value;
                    const l = document.getElementById('log');
                    l.innerText = "Processing...";
                    const encoded = encodeURIComponent(u);
                    window.location.href = "/get-movie?url=" + encoded;
                }
            </script>
        </body>
    </html>
    """

@app.get("/get-movie")
def get_movie_api(request: Request, response: Response):
    debug_logs = []
    try:
        raw_query_bytes = request.scope['query_string']
        raw_query_string = raw_query_bytes.decode("utf-8")
        
        if "url=" in raw_query_string:
            target_url = raw_query_string.split("url=", 1)[1]
            decoded_url = unquote(target_url)
            debug_logs.append(f"🔗 Target: {decoded_url[:60]}...")
            return scrape_movie_data(decoded_url, debug_logs)
        
        return {"error": "Missing url", "logs": debug_logs}

    except Exception as e:
        return {"success": False, "error": str(e), "logs": debug_logs}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
