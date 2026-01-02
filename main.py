from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback
import base64
from urllib.parse import unquote

app = FastAPI()

# البروكسي المعتمد
WORKING_PROXY = "http://176.126.103.194:44214"

def scrape_movie_data(full_url: str, debug_logs: list):
    logs = debug_logs
    logs.append(f"🚀 Start: Connecting via {WORKING_PROXY}")
    
    # 2. تسجيل الرابط الذي سيستخدمه المتصفح للتأكد أنه كامل
    logs.append(f"🔗 Browser Navigating to: {full_url}")
    
    movie_data = None
    snapshot = ""
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=True,
                proxy={"server": WORKING_PROXY},
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", 
                timezone_id="Europe/Moscow"
            )
            context.set_default_timeout(90000) 
            page = context.new_page()

            def handle_response(response):
                nonlocal movie_data
                try:
                    if ("bnsi/movies" in response.url or "cdn/movie" in response.url) and response.status == 200:
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
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "font"] else r.continue_())

            try:
                logs.append("⏳ Loading Page...")
                page.goto(full_url, wait_until="domcontentloaded")
                
                try:
                    page.wait_for_selector("iframe", timeout=20000)
                    page.mouse.click(500, 300) 
                    page.wait_for_timeout(1000)
                    page.mouse.click(500, 300)
                except: pass

                for _ in range(150):
                    if movie_data: break
                    page.wait_for_timeout(100)

            except Exception as e:
                logs.append(f"❌ Navigation Error: {str(e)}")

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
            return {"success": False, "error": f"Browser Error: {str(e)}", "trace": traceback.format_exc()}

# ==============================================================================
# 👇 الواجهة الأمامية الجديدة: صفحة لفحص الروابط بسهولة 👇
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>Movie API Tester</title>
            <style>
                body { font-family: sans-serif; padding: 50px; text-align: center; }
                input { width: 80%; padding: 15px; font-size: 16px; border: 2px solid #ddd; border-radius: 5px; }
                button { padding: 15px 30px; font-size: 16px; background: #28a745; color: white; border: none; cursor: pointer; border-radius: 5px; }
                button:hover { background: #218838; }
                .hint { color: #666; margin-top: 10px; font-size: 14px; }
            </style>
        </head>
        <body>
            <h1>🎬 Movie Link Tester</h1>
            <p>Paste the FULL movie link below. This tool will encode it safely.</p>
            
            <input type="text" id="movieUrl" placeholder="Paste long URL here (https://mercuryglobal...&token=...)" />
            <br><br>
            <button onclick="sendRequest()">🚀 Get Data</button>
            
            <p class="hint">Checking the link via this page guarantees it won't be cut off.</p>

            <script>
                function sendRequest() {
                    var input = document.getElementById("movieUrl").value;
                    if (!input) { alert("Please paste a URL!"); return; }
                    
                    // هذا السطر هو السر: تشفير الرابط ليصبح آمناً للإرسال
                    var encodedUrl = encodeURIComponent(input);
                    
                    // توجيه المتصفح للرابط المشفر
                    window.location.href = "/get-movie?url=" + encodedUrl;
                }
            </script>
        </body>
    </html>
    """

@app.get("/get-movie")
def get_movie_api(request: Request, response: Response):
    debug_logs = []
    try:
        # قراءة الرابط الخام
        raw_query_bytes = request.scope['query_string']
        raw_query_string = raw_query_bytes.decode("utf-8")
        
        debug_logs.append(f"🔍 Server Received Raw: {raw_query_string}")
        
        if "url=" in raw_query_string:
            # استخراج الرابط
            target_url = raw_query_string.split("url=", 1)[1]
            # فك التشفير (مهم جداً الآن لأن الصفحة الجديدة سترسله مشفراً)
            decoded_url = unquote(target_url)
            
            debug_logs.append(f"✂️ After Parsing & Decoding: {decoded_url}")
            
            return scrape_movie_data(decoded_url, debug_logs)
        
        response.status_code = 400
        return {"error": "Missing url parameter", "logs": debug_logs}

    except Exception as e:
        response.status_code = 200
        return {
            "success": False,
            "error": "Server Error",
            "details": str(e),
            "logs": debug_logs,
            "trace": traceback.format_exc()
        }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
