from fastapi import FastAPI, Request
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback
import base64
from urllib.parse import unquote

app = FastAPI()

# البروكسي المعتمد
WORKING_PROXY = "http://176.126.103.194:44214"

def scrape_movie_data(full_url: str):
    logs = []
    logs.append(f"🚀 Start: Connecting via {WORKING_PROXY}")
    logs.append(f"🔗 Received URL: {full_url}") # لنرى الرابط الذي وصل فعلاً
    
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

            # المصيدة
            def handle_response(response):
                nonlocal movie_data
                try:
                    # JSON check
                    if ("bnsi/movies" in response.url or "cdn/movie" in response.url) and response.status == 200:
                        data = response.json()
                        if "hlsSource" in data or "file" in data:
                            movie_data = data
                            logs.append("✅ JSON Data Captured!")
                    
                    # M3U8 Direct check
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
                
                # التعامل مع المشغل
                try:
                    page.wait_for_selector("iframe", timeout=25000)
                    page.mouse.click(500, 300)
                    page.wait_for_timeout(2000)
                    page.mouse.click(500, 300)
                except: pass

                # انتظار البيانات
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
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

@app.get("/")
def home():
    return {"status": "Active", "proxy": WORKING_PROXY}

# 👇👇 التغيير الجوهري هنا 👇👇
# نستخدم Request بدلاً من Query لقراءة الرابط الخام
@app.get("/get-movie")
def get_movie_api(request: Request):
    # الحصول على الرابط الخام بالكامل كما وصل من المتصفح
    raw_query = request.url.query
    
    # استخراج ما بعد "url=" يدوياً للحفاظ على الرموز &
    if "url=" in raw_query:
        target_url = raw_query.split("url=", 1)[1]
        # فك التشفير في حال كان الرابط مشفراً (Encoded)
        target_url = unquote(target_url)
        return scrape_movie_data(target_url)
    
    return {"error": "Missing url parameter"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
