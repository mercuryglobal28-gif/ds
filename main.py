from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from playwright.async_api import async_playwright
import uvicorn
import os
import traceback
import base64
from urllib.parse import unquote
import asyncio

app = FastAPI()

# ==============================================================================
# 💎 إعدادات البروكسي (مفصولة)
# ==============================================================================
PROXY_HOST = "147.45.56.91:8000"
PROXY_USER = "40jSHv"
PROXY_PASS = "RcQr6u"

# ==============================================================================
# 🚀 المتغيرات العامة (Global) للحفاظ على المتصفح مفتوحاً
# ==============================================================================
playwright_instance = None
browser_instance = None

@app.on_event("startup")
async def startup_event():
    """تشغيل المتصفح مرة واحدة عند بدء السيرفر"""
    global playwright_instance, browser_instance
    print("🚀 Starting Global Browser...")
    
    playwright_instance = await async_playwright().start()
    
    browser_instance = await playwright_instance.chromium.launch(
        headless=True,
        proxy={
            "server": f"http://{PROXY_HOST}",
            "username": PROXY_USER,
            "password": PROXY_PASS
        },
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox"
        ]
    )
    print("✅ Global Browser Started Successfully!")

@app.on_event("shutdown")
async def shutdown_event():
    """إغلاق المتصفح عند إيقاف السيرفر"""
    print("🛑 Shutting down browser...")
    if browser_instance:
        await browser_instance.close()
    if playwright_instance:
        await playwright_instance.stop()

# ==============================================================================
# 🧠 منطق الكشط (Async)
# ==============================================================================
async def scrape_movie_data(full_url: str, debug_logs: list):
    logs = debug_logs
    logs.append(f"🚀 Start: Connecting via Async Private Proxy...")
    
    movie_data = None
    snapshot = ""
    page = None
    context = None
    
    try:
        if not browser_instance:
            return {"error": "Browser not initialized"}

        # إنشاء سياق جديد لكل طلب (خفيف جداً)
        context = await browser_instance.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ru-RU", 
            timezone_id="Europe/Moscow",
            ignore_https_errors=True
        )
        
        # مهلة قصيرة للسرعة
        context.set_default_timeout(30000) 
        page = await context.new_page()

        # 1. اعتراض الردود (Response Interception)
        async def handle_response(response):
            nonlocal movie_data
            try:
                if response.status == 200:
                    url = response.url
                    # البحث عن JSON
                    if ("bnsi/movies" in url or "cdn/movie" in url):
                        # نحتاج await هنا لأن json() دالة غير متزامنة
                        try:
                            data = await response.json()
                            if "hlsSource" in data or "file" in data:
                                movie_data = data
                                logs.append("✅ JSON Data Captured!")
                        except: pass
                    
                    # البحث عن m3u8 مباشر
                    if "m3u8" in url and "master" in url:
                         if not movie_data:
                             movie_data = {"direct_m3u8": url}
                             logs.append("✅ Direct M3U8 Found")
            except: pass

        page.on("response", handle_response)

        # 2. حظر الموارد الثقيلة (Route Blocking)
        async def intercept_route(route):
            # قائمة المحظورات لتسريع التصفح
            excluded = ["image", "font", "stylesheet", "other"]
            if route.request.resource_type in excluded:
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", intercept_route)

        # 3. التنقل (Navigation)
        try:
            logs.append(f"⏳ Navigating...")
            # نستخدم commit للسرعة القصوى (بمجرد الاتصال)
            await page.goto(full_url, wait_until="commit", timeout=20000)
            
            # انتظار ذكي (Smart Wait)
            # ننتظر قليلاً لتحميل السكربتات الأساسية
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
            except: pass

            # محاولة النقر (اختياري)
            try:
                # نستخدم evaluate لتنفيذ جافاسكربت مباشرة (أسرع من المحاكاة)
                await page.evaluate("""
                    () => {
                        const iframe = document.querySelector('iframe');
                        if(iframe) {
                            const rect = iframe.getBoundingClientRect();
                            document.elementFromPoint(rect.x + 10, rect.y + 10).click();
                        } else {
                            document.body.click();
                        }
                    }
                """)
            except: pass

            # حلقة انتظار البيانات
            for _ in range(100): # 10 ثواني
                if movie_data: break
                await asyncio.sleep(0.1) # استراحة غير متزامنة

        except Exception as e:
            logs.append(f"⚠️ Navigation Warning: {str(e)[:100]}")

        # التقاط صورة فقط عند الفشل
        if not movie_data:
            try:
                screenshot_bytes = await page.screenshot(type='jpeg', quality=20)
                snapshot = base64.b64encode(screenshot_bytes).decode('utf-8')
                logs.append("📸 Partial Screenshot captured")
            except: pass

    except Exception as e:
        logs.append(f"❌ Error: {str(e)}")
        return {"success": False, "error": str(e), "logs": logs}
    
    finally:
        # تنظيف الموارد (مهم جداً في Async)
        if page: await page.close()
        if context: await context.close()

    if movie_data:
        return movie_data
    else:
        return {
            "success": False, 
            "error": "No Data Found", 
            "logs": logs,
            "screenshot_base64": snapshot
        }

# ==============================================================================
# نقاط الاتصال (Endpoints)
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <body style="font-family:sans-serif; text-align:center; padding:50px; background:#f4f4f4;">
            <h1>🚀 Async Turbo Scraper (Persistent Browser)</h1>
            <input type="text" id="url" style="width:80%; padding:15px; border:1px solid #ddd;" placeholder="Paste URL...">
            <br><br>
            <button onclick="go()" style="padding:15px 30px; background:#007bff; color:white; border:none; cursor:pointer;">Get Data</button>
            <div id="status" style="margin-top:20px; text-align:left; background:white; padding:20px;"></div>
            <script>
                async function go() {
                    const u = document.getElementById('url').value;
                    const s = document.getElementById('status');
                    s.innerHTML = "⏳ Processing async request...";
                    try {
                        const res = await fetch("/get-movie?url=" + encodeURIComponent(u));
                        const data = await res.json();
                        s.innerHTML = "<pre>" + JSON.stringify(data, null, 2) + "</pre>";
                    } catch(e) { s.innerHTML = "Error: " + e; }
                }
            </script>
        </body>
    </html>
    """

@app.get("/get-movie")
async def get_movie_api(request: Request):
    debug_logs = []
    try:
        raw_query = request.scope['query_string'].decode("utf-8")
        if "url=" in raw_query:
            target_url = raw_query.split("url=", 1)[1]
            decoded_url = unquote(target_url)
            
            # استدعاء الدالة غير المتزامنة (await)
            return await scrape_movie_data(decoded_url, debug_logs)
            
        return {"error": "Missing url"}
    except Exception as e:
        return {"error": str(e), "trace": traceback.format_exc()}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    # إعداد uvicorn للعمل مع Async
    uvicorn.run(app, host="0.0.0.0", port=port)
