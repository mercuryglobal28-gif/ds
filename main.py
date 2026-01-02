from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from playwright.sync_api import sync_playwright
import uvicorn
import os
import base64
import traceback

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

def scrape_balanced(target_url: str, proxy_url: str, logs: list):
    logs.append(f"⚖️ Trying Balanced Proxy: {proxy_url}")
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
            
            # مهلة 30 ثانية (وقت كافٍ للتحميل ولكن ليس طويلاً جداً)
            context.set_default_timeout(30000)
            page = context.new_page()

            def handle_response(response):
                nonlocal movie_data
                try:
                    if response.status == 200:
                        # التقاط JSON
                        if ("bnsi/movies" in response.url or "cdn/movie" in response.url):
                            data = response.json()
                            if "hlsSource" in data or "file" in data:
                                movie_data = data
                        
                        # التقاط m3u8 المباشر
                        if "m3u8" in response.url and "master" in response.url:
                             if not movie_data: movie_data = {"direct_m3u8": response.url}
                except: pass

            page.on("response", handle_response)
            
            # ✅ التعديل المهم: نحظر الصور والخطوط فقط
            # السماح بـ media و stylesheet ضروري للمشغل
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "font"] else r.continue_())

            try:
                # ننتظر تحميل هيكل الصفحة فقط
                page.goto(target_url, wait_until="domcontentloaded")
                
                # محاولة تشغيل سريعة
                try:
                    page.wait_for_selector("iframe", timeout=5000)
                    page.mouse.click(500, 300)
                except: pass

                # انتظار البيانات (بحد أقصى 10 ثواني)
                for _ in range(100):
                    if movie_data: 
                        logs.append("✅ Data Found!")
                        break
                    page.wait_for_timeout(100)

            except Exception as e:
                logs.append(f"⚠️ Navigation warning: {str(e)}")

            browser.close()
            return movie_data

        except Exception as e:
            logs.append(f"❌ Browser Error: {str(e)}")
            return None

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <title>Movie Scraper</title>
        <style>
            body { font-family: sans-serif; padding: 40px; background: #f0f2f5; text-align: center; }
            .box { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 600px; margin: auto; }
            input { width: 100%; padding: 12px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
            button { width: 100%; padding: 12px; margin-top: 15px; background: #007bff; color: white; border: none; font-size: 16px; border-radius: 4px; cursor: pointer; }
            button:hover { background: #0056b3; }
            button:disabled { background: #ccc; cursor: not-allowed; }
            #logs { text-align: left; background: #222; color: #0f0; padding: 15px; margin-top: 20px; border-radius: 4px; white-space: pre-wrap; display: none; font-family: monospace; max-height: 400px; overflow-y: auto; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>🎬 Movie Link Processor</h2>
            <p>Paste the full URL below (Safe POST Method)</p>
            <input type="text" id="urlInput" placeholder="https://mercuryglobal...&token=...">
            <button onclick="startScraping()" id="btn">Get Movie Data</button>
            <div id="logs"></div>
        </div>

        <script>
            async function startScraping() {
                const url = document.getElementById('urlInput').value;
                const btn = document.getElementById('btn');
                const logBox = document.getElementById('logs');
                
                if(!url) { alert("Please enter a URL first!"); return; }
                
                btn.disabled = true;
                btn.innerText = "⏳ Processing... (Please wait)";
                logBox.style.display = "block";
                logBox.innerText = "🚀 Sending request to server...\n";

                try {
                    const response = await fetch('/scrape', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: url })
                    });
                    
                    if (!response.ok) {
                        throw new Error(`Server Error: ${response.status}`);
                    }

                    const result = await response.json();
                    logBox.innerText = JSON.stringify(result, null, 2);
                } catch (e) {
                    logBox.innerText = "❌ Error: " + e.message;
                    alert("Connection Failed: " + e.message);
                }
                
                btn.disabled = false;
                btn.innerText = "Get Movie Data";
            }
        </script>
    </body>
    </html>
    """

@app.post("/scrape")
def scrape_endpoint(request: MovieRequest):
    logs = []
    
    # نجرب البروكسي الأول (الأقوى)
    # إذا أردت تجربة الكل، يمكننا إعادة تفعيل الحلقة
    for proxy in PROXY_LIST:
        data = scrape_balanced(request.url, proxy, logs)
        if data:
            return {"success": True, "data": data, "proxy": proxy}
        else:
            logs.append(f"⚠️ Failed on {proxy}, trying next...")
        
    return {"success": False, "error": "All proxies failed", "logs": logs}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
