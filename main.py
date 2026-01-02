from fastapi import FastAPI, Request, Response
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
    logs.append(f"🔗 Targeted URL: {full_url}") # تأكد من السجل هنا
    
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
                # نفتح الرابط الكامل
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

@app.get("/")
def home():
    return {"status": "Active", "proxy": WORKING_PROXY}

# ==============================================================================
# 👇 الحل الجذري (Low-Level Reading) 👇
# ==============================================================================
@app.get("/get-movie")
def get_movie_api(request: Request, response: Response):
    try:
        # نقرأ البايتات الخام مباشرة من بروتوكول الشبكة (ASGI Scope)
        # هذا يتجاوز أي تحليل أو تقسيم يقوم به السيرفر
        raw_query_bytes = request.scope['query_string']
        
        # نحول البايتات إلى نص
        raw_query_string = raw_query_bytes.decode("utf-8")
        
        # الآن لدينا الرابط كما خرج من جهازك تماماً
        if "url=" in raw_query_string:
            # نقسم يدوياً
            target_url = raw_query_string.split("url=", 1)[1]
            
            # فك التشفير إذا لزم الأمر
            decoded_url = unquote(target_url)
            
            # تنظيف الرابط من أي مخلفات قد يضيفها المتصفح في النهاية
            decoded_url = decoded_url.strip()
            
            return scrape_movie_data(decoded_url)
        
        response.status_code = 400
        return {"error": "Missing url parameter", "received_raw": raw_query_string}

    except Exception as e:
        response.status_code = 200
        return {
            "success": False,
            "error": "Server Error",
            "details": str(e),
            "trace": traceback.format_exc()
        }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
