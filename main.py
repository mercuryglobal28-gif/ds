from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from playwright.async_api import async_playwright
import uvicorn
import os
import traceback
import base64
import asyncio
from urllib.parse import unquote, urlparse
import time
import re

app = FastAPI()

# البروكسي المعتمد
WORKING_PROXY = "http://176.126.103.194:44214"

# Regex للكشف عن عناوين الأرقام فقط
NUMERIC_URL_PATTERN = re.compile(r'^https?://[^/]+/(\d+)(?:\.\w+)?$')

async def scrape_movie_data(full_url: str, debug_logs: list):
    logs = debug_logs
    logs.append(f"🚀 Start: Connecting via {WORKING_PROXY}")
    logs.append(f"🔗 Target URL: {full_url}")
    
    target_content = None
    target_url_found = None
    
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
                    "--mute-audio",
                    "--no-first-run"
                ],
                timeout=30000
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", 
                timezone_id="Europe/Moscow",
                viewport={"width": 1920, "height": 1080},
                java_script_enabled=True,
                ignore_https_errors=True
            )
            
            page = await context.new_page()
            page.set_default_timeout(10000)  # 10 ثواني فقط
            
            # ==============================================================
            # 👇 دالة التعامل مع الردود - البحث عن الملف الرقمي فقط 👇
            # ==============================================================
            found_target = False
            
            async def handle_response(response):
                nonlocal target_content, target_url_found, found_target
                
                if found_target:
                    return  # توقف إذا وجدنا المطلوب
                
                try:
                    url = response.url
                    
                    # التحقق إذا كان الرابط يحتوي على أرقام فقط
                    if NUMERIC_URL_PATTERN.match(url):
                        logs.append(f"🎯 FOUND NUMERIC URL: {url}")
                        
                        # حاول الحصول على محتواه
                        try:
                            if response.status == 200:
                                content_type = response.headers.get('content-type', '').lower()
                                
                                if 'application/json' in content_type:
                                    target_content = await response.json()
                                    logs.append("✅ Got JSON content from numeric URL")
                                elif 'text/' in content_type or 'application/' in content_type:
                                    target_content = await response.text()
                                    logs.append(f"✅ Got text content ({len(target_content)} chars)")
                                else:
                                    # للملفات الأخرى، احصل على معلومات عنها فقط
                                    target_content = {
                                        "url": url,
                                        "content_type": content_type,
                                        "status": response.status,
                                        "headers": dict(response.headers)
                                    }
                                    logs.append(f"✅ Got file info (type: {content_type})")
                                
                                target_url_found = url
                                found_target = True
                                
                                # توقف عن معالجة المزيد من الردود
                                page.remove_listener("response", handle_response)
                                
                        except Exception as e:
                            logs.append(f"⚠️ Couldn't read content from {url}: {str(e)}")
                    
                except Exception as e:
                    pass  # تجاهل الأخطاء في معالجة الردود
            
            # إضافة المعالج للردود
            page.on("response", lambda response: asyncio.create_task(handle_response(response)))
            
            # ==============================================================
            # 👇 حظر كل الملفات الغير ضرورية 👇
            # ==============================================================
            async def route_handler(route):
                url = route.request.url
                
                # السماح فقط بـ:
                # 1. الصفحة الرئيسية
                # 2. ملفات HTML
                # 3. ملفات JavaScript
                # 4. طلبات API/XHR/Fetch
                resource_type = route.request.resource_type
                
                # حظر الصور، CSS، الخطوط، الوسائط، وغيرها
                blocked_types = ["image", "stylesheet", "font", "media", "manifest", "texttrack"]
                
                if resource_type in blocked_types:
                    await route.abort()
                elif NUMERIC_URL_PATTERN.match(url):
                    # الملفات الرقمية - تابع لالتقاطها
                    await route.continue_()
                elif "m3u8" in url or "mp4" in url or "video" in url:
                    # ملفات الفيديو - تابع (قد تحتوي على معلومات)
                    await route.continue_()
                else:
                    # السماح للمحتوى الأساسي فقط
                    if resource_type in ["document", "script", "xhr", "fetch"]:
                        await route.continue_()
                    else:
                        await route.abort()
            
            await context.route("**/*", route_handler)
            
            # ==============================================================
            # 👇 تحميل الصفحة 👇
            # ==============================================================
            try:
                logs.append("⏳ Loading page...")
                await page.goto(full_url, wait_until="networkidle", timeout=10000)
                
                # انتظر قصيراً لالتقاط الردود
                logs.append("⏳ Waiting for responses...")
                
                # انتظر بحد أقصى 5 ثواني للعثور على الملف الرقمي
                start_wait = time.time()
                while not found_target and (time.time() - start_wait) < 5:
                    await asyncio.sleep(0.1)
                
                if found_target:
                    logs.append(f"✅ Found target file at: {target_url_found}")
                    await browser.close()
                    
                    return {
                        "success": True,
                        "target_url": target_url_found,
                        "content": target_content,
                        "content_type": type(target_content).__name__,
                        "logs": logs
                    }
                else:
                    logs.append("🔍 No numeric URL files found in network traffic")
                    
                    # لقطة شاشة للتصحيح
                    try:
                        screenshot = await page.screenshot(type='jpeg', quality=20)
                        screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
                        logs.append("📸 Took screenshot for debugging")
                    except:
                        screenshot_b64 = ""
                    
                    await browser.close()
                    
                    return {
                        "success": False,
                        "error": "No numeric URL files detected in network",
                        "logs": logs,
                        "screenshot": screenshot_b64
                    }
                    
            except Exception as e:
                logs.append(f"❌ Page load error: {str(e)}")
                await browser.close()
                
                return {
                    "success": False,
                    "error": f"Page load failed: {str(e)}",
                    "logs": logs
                }
                
    except Exception as e:
        return {
            "success": False,
            "error": f"Browser Error: {str(e)}",
            "trace": traceback.format_exc(),
            "logs": logs
        }

# ==============================================================================
# 👇 واجهة API محسنة مع خيارات متعددة 👇
# ==============================================================================
@app.get("/get-movie")
async def get_movie_api(request: Request, response: Response):
    debug_logs = []
    start_time = time.time()
    
    try:
        # قراءة الرابط الخام
        raw_query_bytes = request.scope['query_string']
        raw_query_string = raw_query_bytes.decode("utf-8")
        
        debug_logs.append(f"🔍 Raw query: {raw_query_string[:100]}...")
        
        if "url=" in raw_query_string:
            # استخراج الرابط
            target_url = raw_query_string.split("url=", 1)[1]
            # فك التشفير
            decoded_url = unquote(target_url)
            
            debug_logs.append(f"🎯 Target URL: {decoded_url[:200]}...")
            
            # تحقق إذا كان الرابط نفسه رقمي
            if NUMERIC_URL_PATTERN.match(decoded_url):
                debug_logs.append("⚠️ Direct numeric URL provided - will fetch directly")
            
            # تنفيذ عملية الـ scraping
            result = await scrape_movie_data(decoded_url, debug_logs)
            
            # حساب الوقت المستغرق
            elapsed_time = time.time() - start_time
            debug_logs.append(f"⏱️ Total time: {elapsed_time:.2f} seconds")
            
            # إضافة الوقت للنتيجة
            if isinstance(result, dict):
                result["processing_time"] = f"{elapsed_time:.2f}s"
            
            return JSONResponse(content=result)
        
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
# 👇 واجهة للفحص المباشر للملفات الرقمية 👇
# ==============================================================================
@app.get("/direct-fetch")
async def direct_fetch_numeric(url: str):
    """جلب محتوى الملف الرقمي مباشرة"""
    start_time = time.time()
    logs = []
    
    try:
        logs.append(f"🎯 Direct fetch for: {url}")
        
        # تحقق إذا كان الرابط رقمي
        if not NUMERIC_URL_PATTERN.match(url):
            return {
                "success": False,
                "error": "URL is not numeric. Must be like: https://example.com/123456",
                "logs": logs
            }
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy={"server": WORKING_PROXY} if WORKING_PROXY else None,
                args=["--no-sandbox"],
                timeout=15000
            )
            
            context = await browser.new_context()
            page = await context.new_page()
            
            # الذهاب مباشرة إلى الرابط الرقمي
            response = await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            
            if response:
                content_type = response.headers.get('content-type', '')
                
                # محاولة قراءة المحتوى بناءً على نوعه
                try:
                    if 'application/json' in content_type:
                        content = await response.json()
                    else:
                        content = await response.text()
                    
                    elapsed = time.time() - start_time
                    
                    return {
                        "success": True,
                        "url": url,
                        "content_type": content_type,
                        "content": content,
                        "size": len(str(content)),
                        "time": f"{elapsed:.2f}s",
                        "logs": logs
                    }
                    
                except Exception as e:
                    elapsed = time.time() - start_time
                    return {
                        "success": False,
                        "error": f"Could not read content: {str(e)}",
                        "url": url,
                        "content_type": content_type,
                        "status": response.status,
                        "time": f"{elapsed:.2f}s",
                        "logs": logs
                    }
            else:
                await browser.close()
                return {
                    "success": False,
                    "error": "No response received",
                    "url": url,
                    "logs": logs
                }
                
    except Exception as e:
        return {
            "success": False,
            "error": f"Direct fetch failed: {str(e)}",
            "url": url,
            "time": f"{time.time() - start_time:.2f}s",
            "logs": logs
        }

# ==============================================================================
# 👇 صفحة واجهة المستخدم 👇
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>Numeric File Finder</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; max-width: 1000px; margin: 0 auto; }
                h1 { color: #333; }
                .container { background: #f5f5f5; padding: 20px; border-radius: 10px; }
                input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; }
                button { background: #4CAF50; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
                button:hover { background: #45a049; }
                .tab { overflow: hidden; border: 1px solid #ccc; background-color: #f1f1f1; }
                .tab button { background-color: inherit; float: left; border: none; outline: none; cursor: pointer; padding: 14px 16px; transition: 0.3s; }
                .tab button:hover { background-color: #ddd; }
                .tab button.active { background-color: #ccc; }
                .tabcontent { display: none; padding: 20px; border: 1px solid #ccc; border-top: none; }
                .result { background: white; padding: 15px; margin: 10px 0; border-radius: 5px; border: 1px solid #ddd; }
                pre { background: #333; color: #fff; padding: 10px; border-radius: 5px; overflow-x: auto; }
            </style>
        </head>
        <body>
            <h1>🔢 Numeric File Finder</h1>
            <p>This tool specifically looks for files with numeric URLs (e.g., https://domain.com/123456789)</p>
            
            <div class="tab">
                <button class="tablinks active" onclick="openTab(event, 'scrape')">Scrape Site</button>
                <button class="tablinks" onclick="openTab(event, 'direct')">Direct Fetch</button>
            </div>
            
            <div id="scrape" class="tabcontent" style="display: block;">
                <h3>Scrape Website for Numeric Files</h3>
                <p>Enter a website URL. The tool will scan network traffic for numeric URLs.</p>
                <input type="text" id="siteUrl" placeholder="https://example.com/movie-page" />
                <button onclick="scrapeSite()">🔍 Scan for Numeric Files</button>
                <div id="scrapeResult"></div>
            </div>
            
            <div id="direct" class="tabcontent">
                <h3>Direct Numeric File Fetch</h3>
                <p>If you already have a numeric URL, fetch it directly:</p>
                <input type="text" id="numericUrl" placeholder="https://example.com/123456789" />
                <button onclick="fetchDirect()">⬇️ Fetch Numeric File</button>
                <div id="directResult"></div>
            </div>
            
            <script>
                function openTab(evt, tabName) {
                    var i, tabcontent, tablinks;
                    tabcontent = document.getElementsByClassName("tabcontent");
                    for (i = 0; i < tabcontent.length; i++) {
                        tabcontent[i].style.display = "none";
                    }
                    tablinks = document.getElementsByClassName("tablinks");
                    for (i = 0; i < tablinks.length; i++) {
                        tablinks[i].className = tablinks[i].className.replace(" active", "");
                    }
                    document.getElementById(tabName).style.display = "block";
                    evt.currentTarget.className += " active";
                }
                
                async function scrapeSite() {
                    const url = document.getElementById('siteUrl').value;
                    if (!url) { alert('Please enter a URL'); return; }
                    
                    const resultDiv = document.getElementById('scrapeResult');
                    resultDiv.innerHTML = '<div class="result">⏳ Scanning for numeric files...</div>';
                    
                    try {
                        const encoded = encodeURIComponent(url);
                        const response = await fetch(`/get-movie?url=${encoded}`);
                        const data = await response.json();
                        
                        let html = '<div class="result">';
                        if (data.success) {
                            html += `<h4>✅ Found Numeric File!</h4>`;
                            html += `<p><strong>URL:</strong> ${data.target_url}</p>`;
                            html += `<p><strong>Type:</strong> ${data.content_type}</p>`;
                            html += `<p><strong>Time:</strong> ${data.processing_time}</p>`;
                            html += `<h5>Content Preview:</h5>`;
                            html += `<pre>${JSON.stringify(data.content, null, 2).substring(0, 1000)}...</pre>`;
                        } else {
                            html += `<h4>❌ No Numeric Files Found</h4>`;
                            html += `<p><strong>Error:</strong> ${data.error}</p>`;
                        }
                        
                        html += `<h5>Logs:</h5><ul>`;
                        data.logs.forEach(log => {
                            html += `<li>${log}</li>`;
                        });
                        html += `</ul></div>`;
                        
                        resultDiv.innerHTML = html;
                    } catch (error) {
                        resultDiv.innerHTML = `<div class="result">❌ Error: ${error.message}</div>`;
                    }
                }
                
                async function fetchDirect() {
                    const url = document.getElementById('numericUrl').value;
                    if (!url) { alert('Please enter a numeric URL'); return; }
                    
                    const resultDiv = document.getElementById('directResult');
                    resultDiv.innerHTML = '<div class="result">⏳ Fetching file...</div>';
                    
                    try {
                        const response = await fetch(`/direct-fetch?url=${encodeURIComponent(url)}`);
                        const data = await response.json();
                        
                        let html = '<div class="result">';
                        if (data.success) {
                            html += `<h4>✅ File Fetched Successfully!</h4>`;
                            html += `<p><strong>URL:</strong> ${data.url}</p>`;
                            html += `<p><strong>Type:</strong> ${data.content_type}</p>`;
                            html += `<p><strong>Size:</strong> ${data.size} bytes</p>`;
                            html += `<p><strong>Time:</strong> ${data.time}</p>`;
                            html += `<h5>Content Preview:</h5>`;
                            html += `<pre>${JSON.stringify(data.content, null, 2).substring(0, 1000)}...</pre>`;
                        } else {
                            html += `<h4>❌ Fetch Failed</h4>`;
                            html += `<p><strong>Error:</strong> ${data.error}</p>`;
                        }
                        
                        if (data.logs && data.logs.length > 0) {
                            html += `<h5>Logs:</h5><ul>`;
                            data.logs.forEach(log => {
                                html += `<li>${log}</li>`;
                            });
                            html += `</ul>`;
                        }
                        
                        html += `</div>`;
                        resultDiv.innerHTML = html;
                    } catch (error) {
                        resultDiv.innerHTML = `<div class="result">❌ Error: ${error.message}</div>`;
                    }
                }
            </script>
        </body>
    </html>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
