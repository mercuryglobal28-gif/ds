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
import time

app = FastAPI()

# البروكسي المعتمد
WORKING_PROXY = "http://176.126.103.194:44214"

# استخدم ThreadPoolExecutor للتنفيذ المتوازي
executor = ThreadPoolExecutor(max_workers=2)

# ذاكرة تخزين مؤقت للنتائج (اختياري)
cache = {}

def scrape_movie_data(full_url: str, debug_logs: list):
    logs = debug_logs
    logs.append(f"🚀 Start: Connecting via {WORKING_PROXY}")
    
    # تسجيل الرابط الذي سيستخدمه المتصفح للتأكد أنه كامل
    logs.append(f"🔗 Browser Navigating to: {full_url}")
    
    movie_data = None
    snapshot = ""
    
    with sync_playwright() as p:
        try:
            # ⚡ التعديل 1: تقليل وقت الإقلاع باستخدام args محسنة
            browser = p.chromium.launch(
                headless=True,
                proxy={"server": WORKING_PROXY},
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-sync",
                    "--disable-default-apps",
                    "--disable-features=TranslateUI",
                    "--disable-background-timer-throttling"
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", 
                timezone_id="Europe/Moscow",
                # ⚡ التعديل 2: تعطيل JavaScript غير الضروري
                java_script_enabled=False,
                # ⚡ التعديل 3: منع تحميل الصور والخطوط مسبقاً
                viewport={'width': 1920, 'height': 1080},
                device_scale_factor=1,
                is_mobile=False,
                has_touch=False,
                reduced_motion="reduce"
            )
            
            # ⚡ التعديل 4: تقليل وقت الانتظار
            context.set_default_timeout(15000)  # 15 ثانية بدلاً من 90
            
            # ⚡ التعديل 5: تعطيل خدمة الخلفية
            context.set_extra_http_headers({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })
            
            page = context.new_page()

            # ⚡ التعديل 6: إضافة معالج للاستجابة السريع
            response_received = False
            response_data = None
            
            def handle_response(response):
                nonlocal movie_data, response_received, response_data
                try:
                    url = response.url
                    # ⚡ التعديل 7: تحقق من الأنواع المطلوبة فقط
                    if (("bnsi/movies" in url or "cdn/movie" in url) and response.status == 200):
                        try:
                            data = response.json()
                            if "hlsSource" in data or "file" in data:
                                movie_data = data
                                response_received = True
                                response_data = data
                                logs.append("✅ JSON Data Captured!")
                                # ⚡ التعديل 8: أوقف التحميل فوراً عند الحصول على البيانات
                                page.evaluate("window.stop()")
                        except:
                            pass
                    
                    if "m3u8" in url and "master" in url:
                        if not movie_data:
                            movie_data = {"direct_m3u8": response.url}
                            response_received = True
                            response_data = {"direct_m3u8": response.url}
                            logs.append("✅ Direct M3U8 Found")
                            page.evaluate("window.stop()")
                except:
                    pass

            page.on("response", handle_response)

            # ⚡ التعديل 9: تحسين intercept_route لتكون أسرع
            def intercept_route(route):
                resource_type = route.request.resource_type
                # منع الأنواع غير الضرورية تماماً
                if resource_type in ["image", "stylesheet", "font", "media"]:
                    route.abort()
                elif resource_type == "script":
                    # السماح فقط بالـ scripts الأساسية
                    url = route.request.url
                    if "jquery" in url or "bootstrap" in url or "video" in url.lower():
                        route.continue_()
                    else:
                        route.abort()
                else:
                    route.continue_()

            page.route("**/*", intercept_route)

            try:
                logs.append("⏳ Loading Page...")
                # ⚡ التعديل 10: استخدام wait_until="commit" بدلاً من domcontentloaded
                page.goto(full_url, wait_until="commit", timeout=10000)
                
                # ⚡ التعديل 11: تقليل وقت انتظار iframe
                try:
                    page.wait_for_selector("iframe", timeout=3000, state="attached")
                    page.mouse.click(500, 300)
                    page.wait_for_timeout(500)
                except:
                    pass

                # ⚡ التعديل 12: تقليل وقت الانتظار الإجمالي
                start_time = time.time()
                timeout = 10  # 10 ثواني كحد أقصى
                
                while not response_received and (time.time() - start_time) < timeout:
                    # تحقق من وجود عناصر الفيديو بسرعة
                    try:
                        video_elements = page.query_selector_all("video, iframe, [data-video], [src*='m3u8'], [src*='mp4']")
                        if video_elements and len(video_elements) > 0:
                            # انقر على أول عنصر فيديو
                            page.mouse.click(500, 300)
                    except:
                        pass
                    
                    page.wait_for_timeout(100)
                    
                    # ⚡ التعديل 13: تحقق من الـ response_received بانتظام
                    if response_received:
                        break

            except Exception as e:
                logs.append(f"⚠️ Navigation Warning: {str(e)}")

            # التقاط صورة فقط إذا لزم الأمر
            if not movie_data:
                try:
                    # ⚡ التعديل 14: التقاط صورة سريعة ذات جودة منخفضة
                    screenshot_bytes = page.screenshot(type='jpeg', quality=10, full_page=False)
                    snapshot = base64.b64encode(screenshot_bytes).decode('utf-8')
                    logs.append("📸 Screenshot captured (low quality)")
                except:
                    pass

            # ⚡ التعديل 15: إغلاق المتصفح بسرعة
            try:
                context.close()
                browser.close()
            except:
                pass
            
            if movie_data:
                return movie_data
            else:
                return {
                    "success": False, 
                    "error": "No Data Found", 
                    "logs": logs,
                    "screenshot_base64": snapshot if snapshot else "",
                    "time_elapsed": time.time() - start_time if 'start_time' in locals() else 0
                }

        except Exception as e:
            return {"success": False, "error": f"Browser Error: {str(e)}", "trace": traceback.format_exc()}

# ⚡ التعديل 16: إضافة دالة async للتعامل مع الخيوط
async def run_scrape_in_thread(full_url: str):
    loop = asyncio.get_event_loop()
    debug_logs = []
    try:
        # تنفيذ في thread منفصل
        result = await loop.run_in_executor(
            executor, 
            lambda: scrape_movie_data(full_url, debug_logs)
        )
        return result
    except Exception as e:
        return {"success": False, "error": f"Thread Error: {str(e)}", "logs": debug_logs}

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>Movie API Tester</title>
            <style>
                body { font-family: sans-serif; padding: 50px; text-align: center; }
                input { width: 80%; padding: 15px; font-size: 16px; border: 2px solid #ddd; border-radius: 5px; }
                button { padding: 15px 30px; font-size: 16px; background: #28a745; color: white; border: none; cursor: pointer; border-radius: 5px; }
                button:hover { background: #218838; }
                .hint { color: #666; margin-top: 10px; font-size: 14px; }
                .loading { display: none; color: #007bff; margin-top: 20px; }
            </style>
        </head>
        <body>
            <h1>🎬 Movie Link Tester</h1>
            <p>Paste the FULL movie link below. This tool will encode it safely.</p>
            
            <input type="text" id="movieUrl" placeholder="Paste long URL here (https://mercuryglobal...&token=...)" />
            <br><br>
            <button onclick="sendRequest()">🚀 Get Data</button>
            <div id="loading" class="loading">⏳ Processing... Please wait (max 15 seconds)</div>
            
            <p class="hint">Checking the link via this page guarantees it won't be cut off.</p>

            <script>
                function sendRequest() {
                    var input = document.getElementById("movieUrl").value;
                    if (!input) { alert("Please paste a URL!"); return; }
                    
                    // إظهار رسالة التحميل
                    document.getElementById("loading").style.display = "block";
                    
                    // تشفير الرابط ليصبح آمناً للإرسال
                    var encodedUrl = encodeURIComponent(input);
                    
                    // توجيه المتصفح للرابط المشفر
                    window.location.href = "/get-movie?url=" + encodedUrl;
                }
            </script>
        </body>
    </html>
    """

@app.get("/get-movie")
async def get_movie_api(request: Request, response: Response):
    debug_logs = []
    try:
        # قراءة الرابط الخام
        raw_query_bytes = request.scope['query_string']
        raw_query_string = raw_query_bytes.decode("utf-8")
        
        debug_logs.append(f"🔍 Server Received Raw: {raw_query_string}")
        
        if "url=" in raw_query_string:
            # استخراج الرابط
            target_url = raw_query_string.split("url=", 1)[1]
            # فك التشفير
            decoded_url = unquote(target_url)
            
            debug_logs.append(f"✂️ After Parsing & Decoding: {decoded_url}")
            
            # ⚡ التعديل 17: استخدام الدالة غير المتزامنة
            start_time = time.time()
            result = await run_scrape_in_thread(decoded_url)
            elapsed_time = time.time() - start_time
            
            # إضافة وقت التنفيذ إلى النتيجة
            if isinstance(result, dict):
                result["execution_time"] = f"{elapsed_time:.2f} seconds"
            
            debug_logs.append(f"⏱️ Total execution time: {elapsed_time:.2f} seconds")
            return result
        
        response.status_code = 400
        return {"error": "Missing url parameter", "logs": debug_logs}

    except Exception as e:
        response.status_code = 200
        return {
            "success": False,
            "error": "Server Error",
            "details": str(e),
            "logs": debug_logs,
            "trace": traceback.format_exc()
        }

# ⚡ التعديل 18: إعدادات uvicorn محسنة للأداء
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        # ⚡ التعديل 19: تحسين إعدادات uvicorn للأداء
        workers=1,  # يمكن زيادته إذا كان الخادم متعدد النوى
        loop="asyncio",
        http="h11",
        timeout_keep_alive=30,
        limit_concurrency=100,
        backlog=2048
    )
