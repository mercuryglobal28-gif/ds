from fastapi import FastAPI, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback
import base64

app = FastAPI()

# البروكسي الذي أثبت نجاحه في جلب الصفحة الروسية
WORKING_PROXY = "http://176.126.103.194:44214"

def scrape_movie_data(full_url: str):
    logs = []
    logs.append(f"🚀 Start: Connecting via {WORKING_PROXY}")
    logs.append(f"🔗 Full URL: {full_url}")
    
    movie_data = None
    snapshot = ""
    
    with sync_playwright() as p:
        try:
            # تشغيل المتصفح مع البروكسي
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
            # زيادة المهلة لضمان تحميل الصفحة الثقيلة
            context.set_default_timeout(90000) 
            page = context.new_page()

            # المصيدة: التقاط أي رابط فيديو (M3U8) أو ملف JSON يظهر في الشبكة
            def handle_response(response):
                nonlocal movie_data
                try:
                    # 1. البحث عن ملفات JSON الخاصة بالفيلم
                    if ("bnsi/movies" in response.url or "cdn/movie" in response.url) and response.status == 200:
                        data = response.json()
                        if "hlsSource" in data or "file" in data:
                            movie_data = data
                            logs.append("✅ JSON Data Captured!")
                    
                    # 2. البحث المباشر عن روابط التشغيل m3u8 (حتى لو لم تظهر في JSON)
                    if "m3u8" in response.url and "master" in response.url:
                         logs.append(f"✅ Direct M3U8 Found: {response.url}")
                         if not movie_data:
                             movie_data = {"direct_m3u8": response.url}

                except: pass

            page.on("response", handle_response)
            
            # حظر الصور والخطوط لتسريع الصفحة
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "font"] else r.continue_())

            try:
                logs.append("⏳ Loading Page...")
                # فتح الرابط كما هو بالضبط دون تعديل
                page.goto(full_url, wait_until="domcontentloaded")
                
                # محاولة التعامل مع المشغل (Iframe)
                try:
                    # ننتظر ظهور الإطار
                    page.wait_for_selector("iframe", timeout=20000)
                    
                    # محاكاة نقرات لتفعيل الفيديو
                    page.mouse.click(500, 300)
                    page.wait_for_timeout(2000)
                    page.mouse.click(500, 300)
                except: 
                    logs.append("⚠️ Could not click play button (might be autoplay)")

                # الانتظار حتى تظهر البيانات
                for _ in range(150): # 15 ثانية
                    if movie_data: break
                    page.wait_for_timeout(100)

            except Exception as e:
                logs.append(f"❌ Navigation Error: {str(e)}")

            # إذا فشل، نلتقط صورة لنرى هل تغيرت رسالة الخطأ
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

@app.get("/get-movie")
def get_movie_api(url: str = Query(..., description="Full URL")):
    # نمرر الرابط مباشرة للدالة
    return scrape_movie_data(url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
