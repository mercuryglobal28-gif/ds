from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from playwright.sync_api import sync_playwright
import uvicorn
import os
import base64

app = FastAPI()

# ==============================================================================
# 🚀 قائمة البروكسيات (تأكد من تجديدها باستمرار)
# ==============================================================================
PROXY_LIST = [
    "http://176.126.103.194:44214", 
    "http://46.161.6.165:8080",
    "http://194.87.238.6:80",
    "http://37.193.52.2:8080",
    "http://109.248.13.234:8080"
]

class MovieRequest(BaseModel):
    url: str

def scrape_fast(target_url: str, proxy_url: str, logs: list):
    logs.append(f"⚡ Trying Fast Proxy: {proxy_url}")
    movie_data = None
    
    with sync_playwright() as p:
        try:
            # تشغيل المتصفح بأقل إعدادات ممكنة للسرعة
            browser = p.chromium.launch(
                headless=True,
                proxy={"server": proxy_url},
                args=[
                    "--no-sandbox", 
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",           # تعطيل الجرافيكس
                    "--disable-dev-shm-usage", # توفير الذاكرة
                    "--blink-settings=imagesEnabled=false" # منع الصور من الجذر
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", timezone_id="Europe/Moscow"
            )
            
            # تقليل مهلة الانتظار العامة
            context.set_default_timeout(15000) 
            page = context.new_page()

            # 🛑 المصيدة الذكية: تلتقط البيانات وتوقف التحميل فوراً
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
            
            # ⛔ حظر الموارد الثقيلة (تسريع بنسبة 60%)
            # نحظر الصور، الخطوط، ملفات التصميم CSS، وملفات الميديا
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "font", "stylesheet", "media", "other"] else r.continue_())

            try:
                # 🚀 التغيير الجوهري: waitUntil='commit'
                # لا ننتظر تحميل الصفحة، ننتظر فقط الاتصال المبدئي
                page.goto(target_url, wait_until="commit", timeout=10000)
                
                # ننتظر قليلاً ليقوم السكربت بطلب البيانات
                for _ in range(50): # 5 ثواني كحد أقصى
                    if movie_data: 
                        logs.append("✅ Data Found Quickly!")
                        break
                    
                    # محاولة نقر سريعة إذا لم تظهر البيانات
                    if _ == 10: # بعد ثانية واحدة
                        try: page.mouse.click(500, 300)
                        except: pass
                        
                    page.wait_for_timeout(100)

            except Exception as e:
                logs.append(f"⚠️ Proxy slow/error: {str(e)}")

            browser.close()
            return movie_data

        except Exception as e:
            logs.append(f"❌ Browser Launch Error: {str(e)}")
            return None

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <title>Turbo Scraper</title>
        <style>
            body { font-family: sans-serif; padding: 40px; background: #eef; text-align: center; }
            input { width: 80%; padding: 15px; border: 1px solid #999; border-radius: 5px; }
            button { width: 80%; padding: 15px; margin-top: 10px; background: #ff4500; color: white; border: none; font-size: 18px; cursor: pointer; }
            #logs { text-align: left; background: #111; color: #0f0; padding: 15px; margin-top: 20px; border-radius: 5px; white-space: pre-wrap; display: none; }
        </style>
    </head>
    <body>
        <h2>⚡ Turbo Link Processor</h2>
        <input type="text" id="urlInput" placeholder="Paste Full URL here...">
        <button onclick="startScraping()" id="btn">🚀 Get Data Fast</button>
        <div id="logs"></div>

        <script>
            async function startScraping() {
                const url = document.getElementById('urlInput').value;
                const btn = document.getElementById('btn');
                const logBox = document.getElementById('logs');
                
                if(!url) return alert("URL Required");
                
                btn.disabled = true;
                btn.innerText = "⚡ Processing...";
                logBox.style.display = "block";
                logBox.innerText = "Running Turbo Engine...\n";

                try {
                    const response = await fetch('/scrape', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: url })
                    });
                    const result = await response.json();
                    logBox.innerText = JSON.stringify(result, null, 2);
                } catch (e) { logBox.innerText = "Error: " + e; }
                
                btn.disabled = false;
                btn.innerText = "🚀 Get Data Fast";
            }
        </script>
    </body>
    </html>
    """

@app.post("/scrape")
def scrape_endpoint(request: MovieRequest):
    logs = []
    
    # تجربة البروكسيات
    for proxy in PROXY_LIST:
        data = scrape_fast(request.url, proxy, logs)
        if data:
            return {"success": True, "data": data, "speed": "Fast", "proxy": proxy}
        
    return {"success": False, "error": "All proxies too slow", "logs": logs}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
