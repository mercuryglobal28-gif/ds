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

# متغير للتحكم في وقت التوقف
TARGET_FOUND = False

async def scrape_movie_data(full_url: str, debug_logs: list):
    logs = debug_logs
    logs.append(f"🚀 Start: Connecting via {WORKING_PROXY}")
    logs.append(f"🔗 Browser Navigating to: {full_url}")
    
    # إعادة تعيين حالة العثور
    global TARGET_FOUND
    TARGET_FOUND = False
    
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
                ],
                timeout=30000
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", 
                timezone_id="Europe/Moscow",
                java_script_enabled=True,
                ignore_https_errors=True
            )
            
            page = await context.new_page()
            page.set_default_timeout(10000)  # 10 ثواني فقط
            
            # ==============================================================
            # دالة الـ response handler المتخصصة
            # ==============================================================
            async def handle_target_response(response):
                global TARGET_FOUND
                
                # إذا تم العثور على الملف المستهدف مسبقاً، تجاهل
                if TARGET_FOUND:
                    return
                
                try:
                    url = response.url
                    
                    # 🔍 البحث عن الملف المستهدف فقط
                    if "/bnsi/movies/" in url and response.status == 200:
                        logs.append(f"🎯 Target File Found: {url}")
                        
                        try:
                            # محاولة الحصول على محتوى JSON
                            data = await response.json()
                            logs.append(f"✅ JSON Data Captured: {len(str(data))} characters")
                            
                            # إعداد النتيجة وإيقاف البحث
                            nonlocal movie_data
                            movie_data = {
                                "success": True,
                                "type": "bnsi_movie_json",
                                "url": url,
                                "data": data,
                                "content_length": len(str(data))
                            }
                            
                            # تحديث حالة العثور لإيقاف المزيد من المعالجة
                            TARGET_FOUND = True
                            
                            # إغلاق المتصفح فوراً
                            logs.append("⚡ Target found - stopping immediately")
                            await browser.close()
                            
                        except Exception as json_error:
                            # إذا لم يكن JSON، حاول الحصول على النص
                            try:
                                text = await response.text()
                                logs.append(f"📄 Text Data Captured: {len(text)} characters")
                                
                                movie_data = {
                                    "success": True,
                                    "type": "bnsi_movie_text",
                                    "url": url,
                                    "data_preview": text[:500],  # أول 500 حرف فقط
                                    "full_length": len(text)
                                }
                                
                                TARGET_FOUND = True
                                logs.append("⚡ Target found (text) - stopping immediately")
                                await browser.close()
                                
                            except Exception as text_error:
                                logs.append(f"⚠️ Could not read response content: {text_error}")
                                
                except Exception as e:
                    logs.append(f"❌ Error in response handler: {str(e)}")
            
            # إضافة الـ handler
            page.on("response", lambda response: asyncio.create_task(handle_target_response(response)))
            
            # ==============================================================
            # تحسين الـ route handling لتسريع العملية
            # ==============================================================
            async def fast_route_handler(route):
                """حجب كل شيء ما عدا المهم جداً"""
                url = route.request.url
                
                # السماح فقط بـ:
                # 1. الصفحة الرئيسية
                # 2. ملفات الـ API التي نبحث عنها
                # 3. ملفات JavaScript الضرورية
                
                if full_url in url or "/bnsi/movies/" in url:
                    await route.continue_()
                elif route.request.resource_type in ["script", "document"]:
                    # السماح لبعض الـ scripts فقط
                    await route.continue_()
                else:
                    # حجب كل شيء آخر
                    await route.abort()
            
            await context.route("**/*", fast_route_handler)
            
            # ==============================================================
            # عملية التحميل السريعة
            # ==============================================================
            try:
                logs.append("⏳ Loading page (fast mode)...")
                
                # تحميل الصفحة بدون انتظار طويل
                response = await page.goto(full_url, wait_until="domcontentloaded", timeout=8000)
                
                if response and response.status != 200:
                    logs.append(f"⚠️ HTTP Status: {response.status}")
                
                # انتظار قصير جداً لالتقاط الردود
                wait_time = 0
                max_wait_time = 5  # أقصى انتظار 5 ثواني
                
                while not TARGET_FOUND and wait_time < max_wait_time:
                    await asyncio.sleep(0.5)
                    wait_time += 0.5
                    
                    # كل ثانية، تحقق مما إذا وجدنا الملف
                    if wait_time % 1 == 0:
                        logs.append(f"⏰ Waiting... {wait_time:.1f}s")
                
                if TARGET_FOUND:
                    logs.append("🎉 Target found successfully!")
                    return movie_data
                    
            except Exception as e:
                logs.append(f"❌ Navigation Error: {str(e)}")
            
            # ==============================================================
            # إذا لم نجد الملف المستهدف
            # ==============================================================
            if not TARGET_FOUND:
                logs.append("🔍 No target file found, trying alternative methods...")
                
                # محاولة بديلة: البحث في الشبكة يدوياً
                try:
                    # الحصول على جميع الردود التي تم استقبالها
                    responses = []
                    
                    # طريقة بسيطة للبحث عن الملف
                    content = await page.content()
                    if "/bnsi/movies/" in content:
                        logs.append("ℹ️ Found /bnsi/movies/ reference in page HTML")
                        
                        # استخراج الأرقام المحتملة
                        import re
                        movie_patterns = re.findall(r'/bnsi/movies/(\d+)', content)
                        if movie_patterns:
                            logs.append(f"🔢 Found {len(movie_patterns)} movie IDs in HTML: {movie_patterns[:5]}")
                    
                except Exception as e:
                    logs.append(f"⚠️ Alternative search failed: {str(e)}")
                
                # لقطة شاشة للتصحيح
                try:
                    screenshot_bytes = await page.screenshot(type='jpeg', quality=30)
                    snapshot = base64.b64encode(screenshot_bytes).decode('utf-8')
                    logs.append("📸 Screenshot captured for debugging")
                except:
                    pass
            
            await browser.close()
            
            if movie_data:
                return movie_data
            else:
                return {
                    "success": False, 
                    "error": "Target file (/bnsi/movies/) not found", 
                    "logs": logs,
                    "screenshot_base64": snapshot
                }

    except Exception as e:
        return {
            "success": False, 
            "error": f"Browser Error: {str(e)}", 
            "trace": traceback.format_exc(),
            "logs": logs
        }

# ==============================================================================
# واجهة API سريعة ومحسنة
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
            
            debug_logs.append(f"🎯 Target URL: {decoded_url}")
            debug_logs.append(f"🔎 Looking for: /bnsi/movies/ files")
            
            # تنفيذ عملية الـ scraping
            result = await scrape_movie_data(decoded_url, debug_logs)
            
            # حساب الوقت المستغرق
            elapsed_time = time.time() - start_time
            debug_logs.append(f"⏱️ Total processing time: {elapsed_time:.2f} seconds")
            
            # إضافة الوقت للنتيجة
            if isinstance(result, dict):
                result["processing_time"] = f"{elapsed_time:.2f}s"
                result["logs"] = debug_logs + (result.get("logs", []))
            
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

# ==============================================================================
# واجهة خاصة للبحث عن الملفات المحددة فقط
# ==============================================================================
@app.get("/find-bnsi-movie")
async def find_bnsi_movie(url: str, movie_id: str = None):
    """واجهة مخصصة للبحث عن ملفات bnsi/movies فقط"""
    start_time = time.time()
    logs = []
    
    logs.append(f"🎯 Starting targeted search for bnsi/movies file")
    logs.append(f"🔗 URL: {url}")
    if movie_id:
        logs.append(f"🔢 Looking for movie ID: {movie_id}")
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy={"server": WORKING_PROXY} if WORKING_PROXY else None,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                timeout=15000
            )
            
            page = await browser.new_page()
            page.set_default_timeout(7000)  # 7 ثواني فقط
            
            target_found = False
            result_data = None
            
            async def targeted_response_handler(response):
                nonlocal target_found, result_data
                
                if target_found:
                    return
                
                resp_url = response.url
                
                # البحث عن الملف المحدد
                if "/bnsi/movies/" in resp_url:
                    if movie_id and movie_id in resp_url:
                        logs.append(f"✅ Found specific movie {movie_id}: {resp_url}")
                    elif not movie_id:
                        logs.append(f"✅ Found bnsi movie file: {resp_url}")
                    
                    try:
                        # محاولة الحصول على JSON
                        data = await response.json()
                        result_data = data
                        logs.append(f"📊 JSON data captured: {len(str(data))} chars")
                    except:
                        # محاولة الحصول على نص
                        try:
                            text = await response.text()
                            result_data = {"text_content": text[:1000]}
                            logs.append(f"📄 Text data captured: {len(text)} chars")
                        except Exception as e:
                            logs.append(f"⚠️ Could not read response: {e}")
                    
                    target_found = True
                    
                    # إغلاق المتصفح فوراً
                    await browser.close()
            
            page.on("response", lambda r: asyncio.create_task(targeted_response_handler(r)))
            
            # تحميل الصفحة بسرعة
            await page.goto(url, wait_until="networkidle", timeout=7000)
            
            # انتظار قصير جداً
            await asyncio.sleep(2)
            
            if not target_found:
                await browser.close()
            
            elapsed = time.time() - start_time
            
            if target_found and result_data:
                return {
                    "success": True,
                    "found": True,
                    "data": result_data,
                    "time": f"{elapsed:.2f}s",
                    "logs": logs
                }
            else:
                return {
                    "success": False,
                    "found": False,
                    "message": "No bnsi/movies file found",
                    "time": f"{elapsed:.2f}s",
                    "logs": logs
                }
                
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "time": f"{time.time() - start_time:.2f}s",
            "logs": logs
        }

# الصفحة الرئيسية
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>BNSI Movie Finder</title>
            <style>
                body { font-family: sans-serif; padding: 50px; text-align: center; background: #f5f5f5; }
                .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                input, textarea { width: 90%; padding: 12px; font-size: 16px; border: 2px solid #ddd; border-radius: 5px; margin: 10px 0; }
                button { padding: 15px 30px; font-size: 16px; background: #007bff; color: white; border: none; cursor: pointer; border-radius: 5px; margin: 5px; }
                button:hover { background: #0056b3; }
                .info { background: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0; text-align: left; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎬 BNSI Movie File Finder</h1>
                <p>This tool specifically searches for <code>/bnsi/movies/</code> files</p>
                
                <div class="info">
                    <strong>How it works:</strong>
                    <ul>
                        <li>Opens the page and immediately looks for <code>/bnsi/movies/</code> URLs</li>
                        <li>Stops processing as soon as the file is found</li>
                        <li>Ignores all other resources (images, CSS, fonts, etc.)</li>
                        <li>Maximum 5-7 seconds per request</li>
                    </ul>
                </div>
                
                <textarea id="movieUrl" rows="2" placeholder="Paste full URL here..."></textarea>
                <br>
                
                <input type="text" id="movieId" placeholder="Optional: Specific movie ID (numbers only)" />
                <br><br>
                
                <button onclick="searchBnsi()">🔍 Find BNSI Movie File</button>
                <button onclick="quickTest()">⚡ Quick Test</button>
                
                <div id="result" style="margin-top: 30px; text-align: left;"></div>
            </div>

            <script>
                function searchBnsi() {
                    var url = document.getElementById("movieUrl").value;
                    var movieId = document.getElementById("movieId").value;
                    
                    if (!url) { 
                        alert("Please paste a URL!"); 
                        return; 
                    }
                    
                    var encodedUrl = encodeURIComponent(url);
                    var apiUrl = "/find-bnsi-movie?url=" + encodedUrl;
                    
                    if (movieId) {
                        apiUrl += "&movie_id=" + movieId;
                    }
                    
                    document.getElementById("result").innerHTML = "<p>⏳ Searching for BNSI movie file...</p>";
                    
                    fetch(apiUrl)
                        .then(response => response.json())
                        .then(data => {
                            var resultDiv = document.getElementById("result");
                            resultDiv.innerHTML = "<h3>Results:</h3>";
                            resultDiv.innerHTML += "<pre>" + JSON.stringify(data, null, 2) + "</pre>";
                        })
                        .catch(error => {
                            document.getElementById("result").innerHTML = "<p>❌ Error: " + error + "</p>";
                        });
                }
                
                function quickTest() {
                    document.getElementById("movieUrl").value = "https://example.com/movie-page";
                    document.getElementById("movieId").value = "224656";
                }
            </script>
        </body>
    </html>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
