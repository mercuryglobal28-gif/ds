from fastapi import FastAPI, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback
import time

app = FastAPI()

# ==============================================================================
# 🎯 البروكسي الذي قمت بفحصه وتأكدت أنه يعمل
# ==============================================================================
# ملاحظة: إذا توقف هذا البروكسي مستقبلاً، فقط استبدل هذا السطر ببروكسي جديد
WORKING_PROXY = "http://176.126.103.194:44214"
# ==============================================================================

def scrape_movie_data(target_url: str):
    logs = []
    logs.append(f"🚀 Start: Using verified proxy {WORKING_PROXY}")
    
    movie_data = None
    
    try:
        with sync_playwright() as p:
            # 1. تشغيل المتصفح مع البروكسي المحدد
            try:
                browser = p.chromium.launch(
                    headless=True,
                    proxy={"server": WORKING_PROXY},
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled"
                    ]
                )
                logs.append("✅ Browser launched successfully")
            except Exception as e:
                return {"success": False, "error": "Browser Launch Failed", "details": str(e)}

            # 2. إعداد السياق (روسيا)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", 
                timezone_id="Europe/Moscow"
            )
            context.set_default_timeout(60000) # 60 ثانية مهلة
            page = context.new_page()

            # 3. تجهيز المصيدة (Sniffer)
            def handle_response(response):
                nonlocal movie_data
                # نبحث عن رد يحتوي على بيانات الفيلم
                if "bnsi/movies" in response.url and response.status == 200:
                    try:
                        data = response.json()
                        # نتأكد أن البيانات مفيدة
                        if "hlsSource" in data or "data" in data:
                            movie_data = data
                            logs.append("🎯 Target Acquired: Movie JSON captured!")
                    except: pass

            page.on("response", handle_response)
            
            # حظر الصور لتخفيف الحمل على البروكسي
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "media", "font"] else r.continue_())

            # 4. الذهاب للرابط
            logs.append(f"⏳ Navigating to URL...")
            try:
                page.goto(target_url, wait_until="domcontentloaded")
                page_title = page.title()
                logs.append(f"📄 Page Title: {page_title}")
                
                if "Access Denied" in page_title or "403" in page_title:
                    logs.append("❌ Blocked: Website detected the proxy.")
                    browser.close()
                    return {"success": False, "diagnosis": "Proxy Detected (403)", "logs": logs}
                
            except Exception as e:
                logs.append(f"❌ Navigation Error: {str(e)}")
                browser.close()
                return {"success": False, "diagnosis": "Proxy Connection Failed/Timeout", "logs": logs}

            # 5. محاولة النقر والانتظار
            if not movie_data:
                logs.append("🖱️ Clicking play button...")
                try: page.mouse.click(500, 300)
                except: pass
                
                logs.append("⏳ Waiting for data packet...")
                # انتظار لمدة 15 ثانية كحد أقصى لظهور البيانات
                for _ in range(150): 
                    if movie_data: break
                    page.wait_for_timeout(100)

            browser.close()
            
            if movie_data:
                return {"success": True, "data": movie_data}
            else:
                return {"success": False, "diagnosis": "Page loaded but no video data found", "logs": logs}

    except Exception as e:
        return {"success": False, "error": "Critical Error", "trace": traceback.format_exc()}

@app.get("/")
def home():
    return {"status": "Active", "proxy": WORKING_PROXY}

@app.get("/get-movie")
def get_movie_api(url: str = Query(..., description="Target URL")):
    return scrape_movie_data(url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
