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
# 💎 إعدادات البروكسي (مفصولة لضمان الاتصال)
# ==============================================================================
PROXY_HOST = "147.45.56.91:8000"  # الايبي والبورت فقط
PROXY_USER = "40jSHv"             # اسم المستخدم
PROXY_PASS = "RcQr6u"             # كلمة المرور
# ==============================================================================

def scrape_movie_data(full_url: str, debug_logs: list):
    logs = debug_logs
    logs.append(f"🚀 Start: Connecting via Private Proxy...")
    
    movie_data = None
    snapshot = ""
    
    with sync_playwright() as p:
        try:
            # تشغيل المتصفح مع إعدادات المصادقة المنفصلة
            browser = p.chromium.launch(
                headless=True,
                proxy={
                    "server": f"http://{PROXY_HOST}",
                    "username": PROXY_USER,
                    "password": PROXY_PASS
                },
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage"
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", 
                timezone_id="Europe/Moscow",
                ignore_https_errors=True
            )
            
            context.set_default_timeout(60000) 
            page = context.new_page()

            # 1. فحص البروكسي (اختياري لكن مفيد للتأكد)
            try:
                page.goto("http://checkip.amazonaws.com", timeout=15000)
                content = page.content()
                # تنظيف النص لعرض الايبي فقط
                ip_clean = page.inner_text("body").strip()
                logs.append(f"✅ Proxy Auth Success! IP: {ip_clean}")
            except Exception as e:
                logs.append(f"⚠️ Proxy Auth Warning: {str(e)}")

            # 2. إعداد المصيدة
            def handle_response(response):
                nonlocal movie_data
                try:
                    if response.status == 200:
                        if ("bnsi/movies" in response.url or "cdn/movie" in response.url):
                            data = response.json()
                            if "hlsSource" in data or "file" in data:
                                movie_data = data
                                logs.append("✅ JSON Data Captured!")
                        
                        if "m3u8" in response.url and "master" in response.url:
                             if not movie_data:
                                 movie_data = {"direct_m3u8": response.url}
                                 logs.append("✅ Direct M3U8 Found")
                except: pass

            page.on("response", handle_response)

            # 3. حظر الموارد الثقيلة
            def intercept_route(route):
                if route.request.resource_type in ["image", "font"]:
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", intercept_route)

            # 4. الذهاب للموقع
            try:
                logs.append(f"⏳ Navigating to Movie URL...")
                page.goto(full_url, wait_until="domcontentloaded", timeout=45000)
                
                # محاولة التشغيل
                try:
                    page.wait_for_selector("iframe", timeout=10000)
                    page.mouse.click(500, 300)
                    page.wait_for_timeout(1000)
                    page.mouse.click(500, 300)
                except: pass

                # انتظار البيانات
                for _ in range(150):
                    if movie_data: break
                    page.wait_for_timeout(100)

            except Exception as e:
                logs.append(f"❌ Navigation Error: {str(e)}")

            # التقاط صورة عند الفشل فقط
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

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <body style="font-family:sans-serif; text-align:center; padding:50px;">
            <h1>🚀 Proxy Fix Updated</h1>
            <p>Paste URL below:</p>
            <input type="text" id="url" style="width:80%; padding:10px;">
            <button onclick="go()">Get Data</button>
            <script>
                async function go() {
                    const u = document.getElementById('url').value;
                    window.location.href = "/get-movie?url=" + encodeURIComponent(u);
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
