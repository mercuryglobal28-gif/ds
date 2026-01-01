from fastapi import FastAPI, HTTPException, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback
import time

app = FastAPI()

# ==========================================
# 🇷🇺 إعدادات البروكسي
# ==========================================
PROXY_SERVER = "http://78.153.4.52:8080" # 👈 غيّر هذا إذا لم يعمل
PROXY_CONFIG = {"server": PROXY_SERVER}
# ==========================================

def scrape_movie(target_url: str):
    # قائمة لتسجيل الأحداث (Log)
    logs = []
    logs.append(f"1. Start: Initiating request via {PROXY_SERVER}")
    
    movie_data = None
    diagnosis = "Unknown Error"
    
    try:
        with sync_playwright() as p:
            # 1. محاولة تشغيل المتصفح
            try:
                browser = p.chromium.launch(
                    headless=True,
                    proxy=PROXY_CONFIG,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled"
                    ]
                )
                logs.append("2. Browser: Launched successfully")
            except Exception as e:
                logs.append(f"❌ Error Launching Browser: {str(e)}")
                return {"success": False, "diagnosis": "Bad Proxy (Connection Refused)", "logs": logs}

            # 2. إعداد الصفحة
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", timezone_id="Europe/Moscow"
            )
            page = context.new_page()
            page.set_default_timeout(45000) # 45 ثانية مهلة

            # مصيدة البيانات
            def handle_response(response):
                nonlocal movie_data
                if "bnsi/movies" in response.url and response.status == 200:
                    try:
                        data = response.json()
                        movie_data = data
                        logs.append("✅ Data Trap: Movie JSON captured!")
                    except: pass
            
            page.on("response", handle_response)

            # 3. محاولة فتح الرابط
            logs.append(f"3. Navigation: Going to URL...")
            try:
                response = page.goto(target_url, wait_until="domcontentloaded")
                status = response.status if response else "Unknown"
                logs.append(f"4. Page Status Code: {status}")
                
                # فحص عنوان الصفحة
                page_title = page.title()
                logs.append(f"5. Page Title: '{page_title}'")
                
                # تحليل المشكلة بناءً على العنوان
                if status == 403 or "Access Denied" in page_title or "403" in page_title:
                    diagnosis = "Proxy Blocked by Website (403)"
                    logs.append("❌ Diagnosis: The website knows you are using a proxy.")
                elif status == 404:
                    diagnosis = "Page Not Found (404)"
                elif not page_title:
                    diagnosis = "Empty Page (Proxy too slow)"
                else:
                    diagnosis = "Page Loaded, Waiting for Video..."

            except Exception as e:
                logs.append(f"❌ Navigation Failed: {str(e)}")
                browser.close()
                return {"success": False, "diagnosis": "Proxy Connection Dead/Timeout", "logs": logs}

            # 4. محاولة التشغيل
            if diagnosis == "Page Loaded, Waiting for Video...":
                try: page.mouse.click(500, 300)
                except: pass
                
                start_time = time.time()
                while time.time() - start_time < 15: # انتظار 15 ثانية
                    if movie_data: break
                    page.wait_for_timeout(200)
                
                if not movie_data:
                    logs.append("❌ Timeout: Video player didn't load api request.")
                    diagnosis = "Video Player Timeout"

            browser.close()

    except Exception as e:
        logs.append(f"🔥 Critical Crash: {str(e)}")
        return {"success": False, "diagnosis": "Server Error", "logs": logs}

    # النتيجة النهائية
    if movie_data:
        return {"success": True, "data": movie_data, "logs": logs}
    else:
        return {"success": False, "diagnosis": diagnosis, "logs": logs}

@app.get("/")
def home():
    return {"status": "Active", "proxy": PROXY_SERVER}

@app.get("/get-movie")
def get_movie_api(url: str = Query(..., description="Movie URL")):
    result = scrape_movie(url)
    if result["success"]:
        return result["data"] # إرجاع البيانات فقط في حال النجاح
    else:
        # إرجاع تقرير الأخطاء في حال الفشل
        return result

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
