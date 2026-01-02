from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from playwright.async_api import async_playwright
import uvicorn
import os
import traceback
import base64
import asyncio
from urllib.parse import unquote
import time

app = FastAPI()

# البروكسي المعتمد
WORKING_PROXY = "http://176.126.103.194:44214"

# كاش للنتائج (اختياري - إذا كانت الروابط تتكرر)
results_cache = {}
CACHE_TIMEOUT = 300  # 5 دقائق

async def scrape_movie_data(full_url: str, debug_logs: list):
    logs = debug_logs
    logs.append(f"🚀 Start: Connecting via {WORKING_PROXY}")
    
    # التحقق من الكاش أولاً
    cache_key = full_url
    if cache_key in results_cache:
        cached_time, cached_result = results_cache[cache_key]
        if time.time() - cached_time < CACHE_TIMEOUT:
            logs.append("⚡ Returning cached result")
            return cached_result
    
    logs.append(f"🔗 Browser Navigating to: {full_url}")
    
    movie_data = None
    snapshot = ""
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy={"server": WORKING_PROXY} if WORKING_PROXY else None,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-extensions",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--disable-accelerated-2d-canvas",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    "--disable-background-networking",
                    "--disable-logging",
                    "--disable-default-apps",
                    "--mute-audio",
                    "--no-first-run",
                    "--no-zygote"
                ],
                timeout=60000  # 60 ثانية لفتح المتصفح
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", 
                timezone_id="Europe/Moscow",
                viewport={"width": 1920, "height": 1080},
                java_script_enabled=True,
                ignore_https_errors=True
            )
            
            # تعطيل الخدمات غير الضرورية لتسريع التحميل
            await context.route("**/*", lambda route: asyncio.create_task(handle_route(route)))
            
            page = await context.new_page()
            page.set_default_timeout(15000)  # 15 ثانية كحد أقصى للانتظار

            # متغير لالتقاط البيانات
            captured_data = []
            
            def handle_response(response):
                try:
                    url = response.url
                    # تحقق من أنواع URLs التي تحتوي على بيانات الفيديو
                    if ("bnsi/movies" in url or "cdn/movie" in url or "m3u8" in url or "master.m3u8" in url):
                        if response.status == 200:
                            # حاول الحصول على JSON أولاً
                            try:
                                data = response.json()
                                captured_data.append({
                                    "url": url,
                                    "type": "json",
                                    "data": data
                                })
                            except:
                                # إذا لم يكن JSON، احصل على النص
                                try:
                                    text = response.text()
                                    if "m3u8" in text or ".ts" in text:
                                        captured_data.append({
                                            "url": url,
                                            "type": "m3u8",
                                            "data": text
                                        })
                                except:
                                    pass
                except:
                    pass
            
            page.on("response", lambda response: handle_response(response))
            
            try:
                # استخدم wait_until="commit" بدلاً من "domcontentloaded" لتسريع التحميل
                logs.append("⏳ Loading Page (fast mode)...")
                response = await page.goto(full_url, wait_until="commit", timeout=15000)
                
                if response and response.status != 200:
                    logs.append(f"⚠️ HTTP Status: {response.status}")
                
                # محاولة سريعة للعثور على iframe أو فيديو
                try:
                    # تحقق من وجود iframes بسرعة
                    iframes = await page.query_selector_all("iframe")
                    if iframes:
                        logs.append(f"🎯 Found {len(iframes)} iframe(s)")
                        # انقر على أول iframe
                        first_iframe = iframes[0]
                        await first_iframe.click(timeout=5000)
                        await asyncio.sleep(1)  # انتظر 1 ثانية فقط
                    
                    # تحقق من وجود عناصر فيديو
                    video_elements = await page.query_selector_all("video")
                    if video_elements:
                        logs.append(f"🎬 Found {len(video_elements)} video element(s)")
                        # حاول تشغيل الفيديو الأول
                        await page.evaluate("""
                            () => {
                                const videos = document.querySelectorAll('video');
                                if (videos.length > 0) {
                                    videos[0].play().catch(e => console.log('Auto-play prevented'));
                                }
                            }
                        """)
                except Exception as e:
                    logs.append(f"ℹ️ No interactive elements found or click failed: {str(e)}")
                
                # انتظار قصير لالتقاط الردود
                await asyncio.sleep(3)
                
                # حاول الحصول على مصادر الفيديو من الصفحة مباشرة
                try:
                    video_sources = await page.evaluate("""
                        () => {
                            const sources = [];
                            // ابحث عن جميع عناصر video
                            document.querySelectorAll('video').forEach(video => {
                                if (video.src) sources.push(video.src);
                                // ابحث عن مصادر داخل source tags
                                video.querySelectorAll('source').forEach(source => {
                                    if (source.src) sources.push(source.src);
                                });
                            });
                            // ابحث عن iframes
                            document.querySelectorAll('iframe').forEach(iframe => {
                                if (iframe.src) sources.push(iframe.src);
                            });
                            // ابحث عن عناصر a تحتوي على m3u8
                            document.querySelectorAll('a[href*="m3u8"], a[href*="mp4"]').forEach(a => {
                                sources.push(a.href);
                            });
                            return sources;
                        }
                    """)
                    
                    if video_sources:
                        logs.append(f"🔍 Found {len(video_sources)} potential video sources in page")
                        for src in video_sources[:5]:  # أول 5 مصادر فقط
                            captured_data.append({
                                "url": src,
                                "type": "direct",
                                "data": src
                            })
                except Exception as e:
                    logs.append(f"ℹ️ Could not extract video sources from page: {str(e)}")
                
            except Exception as e:
                logs.append(f"❌ Navigation Error: {str(e)}")
            
            # تحليل البيانات الملتقطة
            if captured_data:
                logs.append(f"✅ Captured {len(captured_data)} responses")
                # أولوية للبيانات JSON
                json_responses = [d for d in captured_data if d["type"] == "json"]
                if json_responses:
                    movie_data = json_responses[0]["data"]
                else:
                    # ثم مصادر m3u8
                    m3u8_responses = [d for d in captured_data if d["type"] == "m3u8"]
                    if m3u8_responses:
                        movie_data = {"m3u8_content": m3u8_responses[0]["data"][:500]}
                    else:
                        # ثم المصادر المباشرة
                        direct_responses = [d for d in captured_data if d["type"] == "direct"]
                        if direct_responses:
                            movie_data = {"direct_sources": direct_responses[:10]}
            
            # إذا لم نجد بيانات، خذ لقطة شاشة
            if not movie_data:
                try:
                    screenshot_bytes = await page.screenshot(type='jpeg', quality=20)  # جودة أقل لتسريع
                    snapshot = base64.b64encode(screenshot_bytes).decode('utf-8')
                    logs.append("📸 Screenshot captured (low quality)")
                except Exception as e:
                    logs.append(f"⚠️ Screenshot failed: {str(e)}")
            
            await browser.close()
            
            result = None
            if movie_data:
                result = {
                    "success": True,
                    "data": movie_data,
                    "logs": logs,
                    "response_count": len(captured_data)
                }
                # تخزين في الكاش
                results_cache[cache_key] = (time.time(), result)
            else:
                result = {
                    "success": False, 
                    "error": "No video data found", 
                    "logs": logs,
                    "screenshot_base64": snapshot,
                    "captured_responses": len(captured_data)
                }
            
            return result

    except Exception as e:
        return {
            "success": False, 
            "error": f"Browser Error: {str(e)}", 
            "trace": traceback.format_exc(),
            "logs": logs
        }

async def handle_route(route):
    """معالجة الطلبات بحجب الأنواع غير الضرورية"""
    resource_type = route.request.resource_type
    
    # الأنواع المسموحة فقط (الأسرع)
    allowed_types = ["document", "script", "xhr", "fetch"]
    
    if resource_type in allowed_types:
        await route.continue_()
    else:
        # حجب كل شيء آخر
        await route.abort()

# ==============================================================================
# واجهة API محسنة
# ==============================================================================
@app.get("/get-movie")
async def get_movie_api(request: Request, response: Response):
    debug_logs = []
    start_time = time.time()
    
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
            
            # تنفيذ عملية الـ scraping
            result = await scrape_movie_data(decoded_url, debug_logs)
            
            # حساب الوقت المستغرق
            elapsed_time = time.time() - start_time
            debug_logs.append(f"⏱️ Total time: {elapsed_time:.2f} seconds")
            
            # إضافة الوقت للنتيجة
            if isinstance(result, dict):
                result["processing_time"] = f"{elapsed_time:.2f}s"
            
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

# الصفحة الرئيسية (كما هي)
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
            </style>
        </head>
        <body>
            <h1>🎬 Movie Link Tester</h1>
            <p>Paste the FULL movie link below. This tool will encode it safely.</p>
            
            <input type="text" id="movieUrl" placeholder="Paste long URL here (https://mercuryglobal...&token=...)" />
            <br><br>
            <button onclick="sendRequest()">🚀 Get Data</button>
            
            <p class="hint">Checking the link via this page guarantees it won't be cut off.</p>

            <script>
                function sendRequest() {
                    var input = document.getElementById("movieUrl").value;
                    if (!input) { alert("Please paste a URL!"); return; }
                    
                    // تشفير الرابط ليصبح آمناً للإرسال
                    var encodedUrl = encodeURIComponent(input);
                    
                    // توجيه المتصفح للرابط المشفر
                    window.location.href = "/get-movie?url=" + encodedUrl;
                }
            </script>
        </body>
    </html>
    """

# API endpoint سريع للتحقق فقط
@app.get("/quick-check")
async def quick_check(url: str):
    """واجهة أسرع مع إعدادات محدودة"""
    start_time = time.time()
    logs = []
    
    try:
        logs.append(f"🚀 Quick check for: {url[:100]}...")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            
            page = await browser.new_page()
            page.set_default_timeout(10000)  # 10 ثواني فقط
            
            # التقاط الردود السريعة فقط
            m3u8_urls = []
            def quick_response_handler(response):
                if "m3u8" in response.url:
                    m3u8_urls.append(response.url)
            
            page.on("response", lambda resp: quick_response_handler(resp))
            
            # انتقل للصفحة بدون انتظار كامل
            await page.goto(url, wait_until="networkidle", timeout=10000)
            
            # انتظر 2 ثانية فقط لالتقاط الردود
            await asyncio.sleep(2)
            
            await browser.close()
            
            elapsed = time.time() - start_time
            
            if m3u8_urls:
                return {
                    "success": True,
                    "m3u8_urls": m3u8_urls[:5],  # أول 5 فقط
                    "time": f"{elapsed:.2f}s",
                    "logs": logs
                }
            else:
                return {
                    "success": False,
                    "message": "No m3u8 URLs found in quick scan",
                    "time": f"{elapsed:.2f}s",
                    "logs": logs
                }
                
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "time": f"{time.time() - start_time:.2f}s"
        }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
