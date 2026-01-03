from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback
import base64
from urllib.parse import unquote
import asyncio
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# ==============================================================================
# 💎 إعدادات البروكسي (مفصولة لضمان الاتصال)
# ==============================================================================
PROXY_HOST = "147.45.56.91:8000"  # الايبي والبورت فقط
PROXY_USER = "40jSHv"             # اسم المستخدم
PROXY_PASS = "RcQr6u"

# ==============================================================================
# 🚀 إعدادات التحسين
# ==============================================================================
# استخدام thread pool للتعامل مع الطلبات المتزامنة
executor = ThreadPoolExecutor(max_workers=5)

# تخزين المتصفح لاستخدامه في جلسات متعددة
_browser = None

def init_browser():
    """تهيئة المتصفح مرة واحدة وإعادة استخدامه"""
    global _browser
    if _browser is None:
        with sync_playwright() as p:
            _browser = p.chromium.launch(
                headless=True,
                proxy={
                    "server": f"http://{PROXY_HOST}",
                },
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",  # إيقاف GPU لتسريع التشغيل
                    "--disable-software-rasterizer",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--disable-sync",
                    "--disable-translate",
                    "--no-first-run",
                    "--no-zygote",
                    "--single-process",  # وضع عملية واحدة
                    "--use-gl=disabled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
                timeout=30000  # وقت أقل للبدء
            )
    return _browser

async def scrape_movie_data_async(full_url: str, debug_logs: list):
    """النسخة غير المتزامنة للكشط"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor, 
        lambda: sync_scrape_movie_data(full_url, debug_logs)
    )

def sync_scrape_movie_data(full_url: str, debug_logs: list):
    """الكشط المتزامن (للتنفيذ في thread pool)"""
    logs = debug_logs
    logs.append(f"🚀 Start: Connecting via Private Proxy...")
    
    movie_data = None
    snapshot = ""
    
    try:
        # استخدام المتصفح المشترك
        browser = init_browser()
        
        # إعداد context جديد
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ru-RU", 
            timezone_id="Europe/Moscow",
            ignore_https_errors=True,
            viewport={'width': 1280, 'height': 720},
            device_scale_factor=1,
            java_script_enabled=True,
            has_touch=False,
            is_mobile=False,
            reduced_motion="reduce"
        )
        
        context.set_default_timeout(30000)  # تقليل الوقت الانتظار
        
        page = context.new_page()

        # 1. إعداد معالج الردود أولاً
        def handle_response(response):
            nonlocal movie_data
            try:
                url = response.url.lower()
                status = response.status
                
                # تصفية أكثر دقة للروابط
                if status == 200:
                    if ("movie" in url or "video" in url or "stream" in url or "play" in url):
                        try:
                            if "json" in response.headers.get('content-type', ''):
                                data = response.json()
                                # البحث عن مفاتيح معروفة
                                if any(key in str(data).lower() for key in ['hls', 'm3u8', 'mp4', 'file', 'source', 'url']):
                                    movie_data = data
                                    logs.append(f"✅ JSON Data Captured from {url[:50]}...")
                        except:
                            # قد يكون النص مباشرة
                            try:
                                text = response.text()
                                if 'm3u8' in text or '.mp4' in text:
                                    movie_data = {"direct_url": text.strip()}
                                    logs.append(f"✅ Direct URL Found in text response")
                            except:
                                pass
            except Exception as e:
                logs.append(f"⚠️ Response handler error: {str(e)[:100]}")

        page.on("response", handle_response)

        # 2. حظر الموارد غير الضرورية بشكل أكثر صرامة
        def intercept_route(route):
            req = route.request
            url = req.url.lower()
            
            # قائمة بالنطاقات/الأنواع التي نريد حظرها
            blocked_resources = [
                'analytics', 'track', 'pixel', 'beacon', 'ads', 
                'adservice', 'doubleclick', 'facebook.com/tr',
                'googlesyndication', 'google-analytics', 'stats',
                'logger', 'monitor', 'metric'
            ]
            
            # حظر الصور والخطوط وبعض الموارد الأخرى
            if (req.resource_type in ["image", "font", "media", "stylesheet"] or
                any(blocked in url for blocked in blocked_resources)):
                route.abort()
            else:
                route.continue_()

        page.route("**/*", intercept_route)

        # 3. الذهاب للموقع
        try:
            logs.append(f"⏳ Navigating to Movie URL...")
            
            # استخدام wait_until="commit" للسرعة
            page.goto(full_url, wait_until="commit", timeout=20000)
            
            # انتظار قصير لتحميل DOM
            page.wait_for_load_state("domcontentloaded", timeout=5000)
            
            # البحث السريع عن iframe أو فيديو
            try:
                # محاولة إيجاد iframes
                iframes = page.query_selector_all("iframe")
                if iframes:
                    logs.append(f"🎯 Found {len(iframes)} iframes")
                    
                # محاولة النقر في مركز الصفحة
                viewport = page.viewport_size
                if viewport:
                    page.mouse.click(viewport["width"] // 2, viewport["height"] // 2)
                    
                # انتظار قصير جداً لرد الفعل
                page.wait_for_timeout(1000)
                
                # البحث عن عناصر تشغيل الفيديو
                video_elements = page.query_selector_all("video, [data-video], [data-src*='video']")
                if video_elements:
                    logs.append(f"🎬 Found {len(video_elements)} video elements")
                    
            except Exception as e:
                logs.append(f"ℹ️ UI interaction skipped: {str(e)[:50]}")

            # الانتظار بذكاء للبيانات
            max_wait_time = 10  # ثواني
            check_interval = 0.2  # ثانية
            waited = 0
            
            while not movie_data and waited < max_wait_time:
                page.wait_for_timeout(check_interval * 1000)
                waited += check_interval
                
                # خروج مبكر إذا وجدنا البيانات
                if movie_data:
                    break
            
            logs.append(f"⏱️ Total wait time: {waited:.1f}s")

        except Exception as e:
            logs.append(f"❌ Navigation Error: {str(e)[:100]}")

        # التقاط صورة فقط عند الضرورة
        if not movie_data:
            try:
                # التقاط جزء فقط من الصفحة للسرعة
                screenshot_bytes = page.screenshot(
                    type='jpeg', 
                    quality=20,  # جودة منخفضة للسرعة
                    clip={'x': 0, 'y': 0, 'width': 800, 'height': 400}
                )
                snapshot = base64.b64encode(screenshot_bytes).decode('utf-8')
                logs.append("📸 Partial screenshot captured")
            except Exception as e:
                logs.append(f"⚠️ Screenshot failed: {str(e)[:50]}")

        # تنظيف السياق
        try:
            context.close()
        except:
            pass

        if movie_data:
            # تقليل حجم البيانات المرجعة
            if isinstance(movie_data, dict) and len(str(movie_data)) > 10000:
                movie_data = {k: v for k, v in movie_data.items() if k in ['hlsSource', 'file', 'url', 'direct_url', 'direct_m3u8']}
            return movie_data
        else:
            return {
                "success": False, 
                "error": "No Data Found", 
                "logs": logs[:20],  # تقليل عدد السجلات
                "screenshot_base64": snapshot[:50000] if snapshot else ""  # تقليل حجم الصورة
            }

    except Exception as e:
        return {"success": False, "error": f"Critical Error: {str(e)[:200]}", "logs": logs[:10]}

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <body style="font-family:sans-serif; text-align:center; padding:50px;">
            <h1>🚀 Proxy Fix Updated - Ultra Fast Version</h1>
            <p>Paste URL below:</p>
            <input type="text" id="url" style="width:80%; padding:10px; margin:10px;" 
                   placeholder="https://example.com/movie">
            <button onclick="go()" style="padding:10px 20px;">Get Data</button>
            <div id="status" style="margin:20px; padding:10px;"></div>
            
            <script>
                async function go() {
                    const urlInput = document.getElementById('url');
                    const statusDiv = document.getElementById('status');
                    const url = urlInput.value.trim();
                    
                    if (!url) {
                        statusDiv.innerHTML = '<p style="color:red;">Please enter a URL</p>';
                        return;
                    }
                    
                    statusDiv.innerHTML = '<p>⏳ Processing... Please wait</p>';
                    
                    try {
                        const response = await fetch('/get-movie?url=' + encodeURIComponent(url));
                        const data = await response.json();
                        
                        if (data.success !== false && data.error) {
                            statusDiv.innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                        } else {
                            statusDiv.innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                        }
                    } catch (error) {
                        statusDiv.innerHTML = '<p style="color:red;">Error: ' + error.message + '</p>';
                    }
                }
            </script>
        </body>
    </html>
    """

@app.get("/get-movie")
async def get_movie_api(request: Request, response: Response):
    debug_logs = []
    try:
        # معالجة سريعة للاستعلام
        query_string = request.scope['query_string'].decode("utf-8")
        
        if "url=" in query_string:
            target_url = query_string.split("url=", 1)[1]
            decoded_url = unquote(target_url)
            
            # التحقق الأساسي من الرابط
            if not decoded_url.startswith(('http://', 'https://')):
                return {"error": "Invalid URL", "logs": ["URL must start with http:// or https://"]}
            
            debug_logs.append(f"🔗 Target: {decoded_url[:80]}...")
            
            # استخدام النسخة غير المتزامنة للكشط
            result = await scrape_movie_data_async(decoded_url, debug_logs)
            
            # إضافة معلومات الأداء
            if isinstance(result, dict):
                result["performance"] = {
                    "logs_count": len(debug_logs),
                    "timestamp": os.times().elapsed
                }
            
            return result
        
        return {"error": "Missing url parameter", "logs": debug_logs}

    except Exception as e:
        return {"success": False, "error": str(e)[:200], "logs": debug_logs}

@app.on_event("shutdown")
async def shutdown_event():
    """تنظيف الموارد عند إيقاف التطبيق"""
    global _browser
    if _browser:
        _browser.close()
    executor.shutdown(wait=False)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    
    # إعدادات uvicorn محسنة للأداء
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        workers=1,  # استخدام worker واحد مع thread pool
        loop="asyncio",
        log_level="warning",  # تقليل السجلات
        access_log=False,  # إيقاف سجلات الوصول للسرعة
        timeout_keep_alive=30
    )
