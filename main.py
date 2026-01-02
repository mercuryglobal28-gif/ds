from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from playwright.sync_api import sync_playwright
import uvicorn
import os
import base64
import traceback
from urllib.parse import unquote

app = FastAPI()

# قائمة البروكسيات
PROXY_LIST = [
    "http://176.126.103.194:44214", 
    "http://46.161.6.165:8080",
    "http://194.87.238.6:80",
    "http://37.193.52.2:8080",
    "http://109.248.13.234:8080"
]

class MovieRequest(BaseModel):
    url: str

def scrape_logic(target_url: str, proxy_url: str, logs: list):
    logs.append(f"🔄 Trying Proxy: {proxy_url}")
    movie_data = None
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=True,
                proxy={"server": proxy_url},
                args=[
                    "--no-sandbox", 
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage"
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", timezone_id="Europe/Moscow"
            )
            
            context.set_default_timeout(30000)
            page = context.new_page()

            def handle_response(response):
                nonlocal movie_data
                try:
                    if response.status == 200:
                        if ("bnsi/movies" in response.url or "cdn/movie" in response.url):
                            data = response.json()
                            if "hlsSource" in data or "file" in data:
                                movie_data = data
                        if "m3u8" in response.url and "master" in response.url:
                             if not movie_data: movie_data = {"direct_m3u8": response.url}
                except: pass

            page.on("response", handle_response)
            
            # السماح بالملفات الضرورية فقط
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "font"] else r.continue_())

            try:
                page.goto(target_url, wait_until="domcontentloaded")
                
                try:
                    page.wait_for_selector("iframe", timeout=5000)
                    page.mouse.click(500, 300)
                except: pass

                for _ in range(80): # 8 ثواني انتظار
                    if movie_data: break
                    page.wait_for_timeout(100)

            except Exception as e:
                logs.append(f"⚠️ Navigation error: {str(e)}")

            browser.close()
            return movie_data

        except Exception as e:
            logs.append(f"❌ Browser Error: {str(e)}")
            return None

def run_scraper(url: str):
    logs = []
    # تجربة البروكسيات بالتسلسل
    for proxy in PROXY_LIST:
        data = scrape_logic(url, proxy, logs)
        if data:
            return {"success": True, "data": data, "proxy": proxy}
    return {"success": False, "error": "All proxies failed", "logs": logs}

# ==============================================================================
# 1️⃣ الصفحة الرئيسية (HTML UI)
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <title>Universal Scraper</title>
        <style>
            body { font-family: sans-serif; padding: 20px; text-align: center; background: #f4f4f9; }
            .container { background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: auto; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
            input { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 5px; margin-bottom: 10px; }
            button { width: 100%; padding: 10px; background: #28a745; color: white; border: none; cursor: pointer; font-size: 16px; border-radius: 5px; }
            button:disabled { background: #ccc; }
            #output { text-align: left; background: #222; color: lime; padding: 15px; margin-top: 15px; display: none; white-space: pre-wrap; max-height: 400px; overflow: auto; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🎬 API Tester</h2>
            <input type="text" id="urlInput" placeholder="Paste full URL here...">
            <button onclick="start()" id="btn">Get Data</button>
            <div id="output"></div>
        </div>
        <script>
            async function start() {
                const url = document.getElementById('urlInput').value;
                const btn = document.getElementById('btn');
                const out = document.getElementById('output');
                if(!url) return alert("URL Required");
                
                btn.disabled = true; btn.innerText = "Processing...";
                out.style.display = "block"; out.innerText = "⏳ Request sent...";
                
                try {
                    // نستخدم POST هنا للزر لضمان عدم قطع الرابط
                    const res = await fetch('/scrape', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({url: url})
                    });
                    const data = await res.json();
                    out.innerText = JSON.stringify(data, null, 2);
                } catch(e) { out.innerText = "Error: " + e; }
                
                btn.disabled = false; btn.innerText = "Get Data";
            }
        </script>
    </body>
    </html>
    """

# ==============================================================================
# 2️⃣ نقطة الاتصال للزر (POST) - لا تقطع الرابط
# ==============================================================================
@app.post("/scrape")
def api_scrape_post(req: MovieRequest):
    return run_scraper(req.url)

# ==============================================================================
# 3️⃣ نقطة الاتصال للمتصفح المباشر والأندرويد (GET) - تم إصلاحها!
# ==============================================================================
@app.get("/get-movie")
def api_scrape_get(request: Request):
    try:
        # الحل السحري لقراءة الرابط كاملاً
        raw_query = request.scope['query_string'].decode("utf-8")
        if "url=" in raw_query:
            target_url = raw_query.split("url=", 1)[1]
            decoded_url = unquote(target_url)
            return run_scraper(decoded_url)
        return {"error": "Missing url parameter"}
    except Exception as e:
        return {"error": str(e), "trace": traceback.format_exc()}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
