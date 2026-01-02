from fastapi import FastAPI, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback
import base64
from urllib.parse import urlparse, parse_qs

app = FastAPI()

# البروكسي الحالي (تأكد أنه لا يزال يعمل)
WORKING_PROXY = "http://176.126.103.194:44214"

def get_real_url(original_url: str):
    try:
        if "url=" in original_url:
            parsed = urlparse(original_url)
            query_params = parse_qs(parsed.query)
            if "url" in query_params:
                return query_params["url"][0]
    except: pass
    return original_url

def scrape_movie_data(input_url: str):
    target_url = get_real_url(input_url)
    
    logs = []
    logs.append(f"🚀 Start: Connecting via {WORKING_PROXY}")
    logs.append(f"🔗 Target: {target_url}")
    
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
            
            # 👇👇 التعديل الجوهري: إضافة الهيدرز لخداع الموقع 👇👇
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", 
                timezone_id="Europe/Moscow",
                extra_http_headers={
                    "Referer": "https://mercuryglobal28-gif.github.io/", # نوهمهم أننا قادمون من الموقع الأصلي
                    "Origin": "https://mercuryglobal28-gif.github.io/"
                }
            )
            
            # زيادة الوقت إلى 90 ثانية للبروكسيات البطيئة
            context.set_default_timeout(90000) 
            page = context.new_page()

            def handle_response(response):
                nonlocal movie_data
                if ("bnsi/movies" in response.url or "cdn/movie" in response.url) and response.status == 200:
                    try:
                        data = response.json()
                        if "hlsSource" in data or "file" in data:
                            movie_data = data
                            logs.append("✅ Data Captured!")
                    except: pass

            page.on("response", handle_response)
            
            # السماح بالسكربتات فقط (لأن المشغل يحتاجها)
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "font", "stylesheet"] else r.continue_())

            try:
                logs.append("⏳ Loading Page...")
                page.goto(target_url, wait_until="domcontentloaded")
                logs.append(f"📄 Page Title Loaded: {page.title()}")
                
                # محاولة التشغيل
                try: 
                    page.wait_for_selector("body", state="visible", timeout=10000)
                    page.mouse.click(500, 300)
                except: pass
                
                # انتظار البيانات
                for _ in range(200):
                    if movie_data: break
                    page.wait_for_timeout(100)

            except Exception as e:
                logs.append(f"❌ Navigation Error: {str(e)}")
                # 📸 التقاط صورة عند الخطأ
                try:
                    screenshot_bytes = page.screenshot(type='jpeg', quality=30)
                    snapshot = base64.b64encode(screenshot_bytes).decode('utf-8')
                    logs.append("📸 Screenshot taken (check screenshot_base64)")
                except: pass

            browser.close()
            
            if movie_data:
                return movie_data
            else:
                # 📸 التقاط صورة في حال انتهاء الوقت دون بيانات
                return {
                    "success": False, 
                    "error": "Timeout - No Data", 
                    "logs": logs,
                    "screenshot_base64": snapshot
                }

        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

@app.get("/")
def home():
    return {"status": "Active"}

@app.get("/get-movie")
def get_movie_api(url: str = Query(..., description="Full URL")):
    return scrape_movie_data(url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
