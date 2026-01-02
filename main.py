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
NUMERIC_URL_PATTERN = re.compile(r'^https?://[^/]+/(\d+)(?:/|$|\?|\.)')

async def scrape_movie_data(full_url: str, debug_logs: list):
    logs = debug_logs
    logs.append(f"🚀 Start: Connecting via {WORKING_PROXY}")
    logs.append(f"🔗 Target URL: {full_url[:200]}...")
    
    target_content = None
    target_url_found = None
    
    try:
        async with async_playwright() as p:
            # إعداد المتصفح مع تحسينات السرعة
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
                    "--no-first-run",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-web-security",
                    "--disable-features=BlockInsecurePrivateNetworkRequests"
                ],
                timeout=30000
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", 
                timezone_id="Europe/Moscow",
                viewport={"width": 1280, "height": 720},
                java_script_enabled=True,
                ignore_https_errors=True
            )
            
            page = await context.new_page()
            page.set_default_timeout(15000)  # 15 ثانية
            
            # ==============================================================
            # 👇 متغيرات لتتبع الردود 👇
            # ==============================================================
            found_target = False
            all_responses = []
            numeric_responses = []
            
            # ==============================================================
            # 👇 دالة التعامل مع الردود 👇
            # ==============================================================
            def handle_response(response):
                nonlocal target_content, target_url_found, found_target
                
                if found_target:
                    return
                
                try:
                    url = response.url
                    all_responses.append({
                        "url": url,
                        "status": response.status,
                        "type": response.request.resource_type
                    })
                    
                    # البحث عن روابط رقمية في أي جزء من الـ URL
                    # مثل: /123456789 أو /video/12345 أو ?id=123456
                    if re.search(r'/(\d{6,})', url) or re.search(r'[=&](\d{6,})', url):
                        logs.append(f"🔍 Found numeric pattern in URL: {url[:200]}")
                        
                        # تسجيل الاستجابة الرقمية
                        numeric_responses.append({
                            "url": url,
                            "status": response.status
                        })
                        
                        # إذا كان الرابط يحتوي على أرقام فقط في المسار الرئيسي
                        path = urlparse(url).path
                        if re.match(r'^/\d+$', path) or re.match(r'^/\d+\.\w+$', path):
                            logs.append(f"🎯 STRONG MATCH - Pure numeric path: {url}")
                            
                            # حاول الحصول على المحتوى
                            async def fetch_content():
                                try:
                                    if response.status == 200:
                                        content_type = response.headers.get('content-type', '').lower()
                                        
                                        if 'application/json' in content_type:
                                            content = await response.json()
                                            logs.append(f"✅ Got JSON content ({len(str(content))} chars)")
                                        elif 'text/' in content_type:
                                            content = await response.text()
                                            logs.append(f"✅ Got text content ({len(content)} chars)")
                                        elif 'video/' in content_type or 'audio/' in content_type:
                                            content = {
                                                "url": url,
                                                "content_type": content_type,
                                                "size": response.headers.get('content-length', 'unknown')
                                            }
                                            logs.append(f"✅ Got media file info")
                                        else:
                                            # للملفات الأخرى
                                            content = {
                                                "url": url,
                                                "content_type": content_type,
                                                "status": response.status,
                                                "headers": dict(response.headers)
                                            }
                                            logs.append(f"✅ Got other file (type: {content_type})")
                                        
                                        target_content = content
                                        target_url_found = url
                                        found_target = True
                                        
                                except Exception as e:
                                    logs.append(f"⚠️ Couldn't read content: {str(e)}")
                            
                            # تشغيل في الخلفية
                            asyncio.create_task(fetch_content())
                            
                except Exception as e:
                    logs.append(f"⚠️ Response handler error: {str(e)}")
            
            # إضافة المعالج للردود
            page.on("response", handle_response)
            
            # ==============================================================
            # 👇 إعداد الـ Route Handler 👇
            # ==============================================================
            async def route_handler(route):
                url = route.request.url
                resource_type = route.request.resource_type
                
                # السماح فقط بالملفات الأساسية
                allowed_types = ["document", "script", "xhr", "fetch"]
                
                # السماح أيضًا بملفات الفيديو والصوت
                if resource_type == "media":
                    await route.continue_()
                elif resource_type in allowed_types:
                    await route.continue_()
                else:
                    # حجب الصور، CSS، الخطوط، إلخ
                    await route.abort()
            
            await context.route("**/*", route_handler)
            
            # ==============================================================
            # 👇 تحميل الصفحة بسرعة 👇
            # ==============================================================
            try:
                logs.append("⏳ Loading page (fast mode)...")
                
                # استخدم load فقط، لا تنتظر networkidle
                response = await page.goto(full_url, wait_until="load", timeout=10000)
                
                if response:
                    logs.append(f"✅ Page loaded with status: {response.status}")
                else:
                    logs.append("⚠️ Page loaded but no response object")
                
                # انتظر بضع ثوانٍ فقط لاكتشاف الردود
                logs.append("⏳ Listening for network responses (5 seconds)...")
                
                # انتظر فترة قصيرة للكشف عن الردود
                start_time = time.time()
                while time.time() - start_time < 5 and not found_target:
                    await asyncio.sleep(0.1)
                
                # إذا لم نجد هدف، جرب تحفيز الصفحة
                if not found_target:
                    logs.append("🔍 No target found yet, trying to interact with page...")
                    
                    # جرب النقر على العناصر
                    try:
                        # ابحث عن فيديو أو iframe وانقر
                        video_elements = await page.query_selector_all("video, iframe, [data-video], [data-src*='video']")
                        if video_elements:
                            logs.append(f"🎬 Found {len(video_elements)} video/iframe elements")
                            for i, element in enumerate(video_elements[:3]):  # أول 3 فقط
                                try:
                                    await element.click(timeout=2000)
                                    logs.append(f"✅ Clicked element {i+1}")
                                    await asyncio.sleep(1)  # انتظر ثانية بعد النقر
                                except:
                                    pass
                    except Exception as e:
                        logs.append(f"⚠️ Interaction failed: {str(e)}")
                    
                    # انتظر أكثر بعد التفاعل
                    await asyncio.sleep(2)
                
                # ==============================================================
                # 👇 تحليل النتائج 👇
                # ==============================================================
                if found_target:
                    logs.append(f"✅ Found target file: {target_url_found}")
                    await browser.close()
                    
                    return {
                        "success": True,
                        "target_url": target_url_found,
                        "content": target_content,
                        "content_type": type(target_content).__name__ if target_content else "unknown",
                        "logs": logs,
                        "total_responses": len(all_responses),
                        "numeric_responses": numeric_responses
                    }
                else:
                    logs.append(f"🔍 Scan complete. Total responses: {len(all_responses)}, Numeric responses: {len(numeric_responses)}")
                    
                    # عرض بعض الردود الرقمية للمساعدة في التصحيح
                    if numeric_responses:
                        logs.append("📊 Numeric responses found (but not pure numeric paths):")
                        for i, resp in enumerate(numeric_responses[:5]):  # أول 5 فقط
                            logs.append(f"  {i+1}. {resp['url'][:200]} (status: {resp['status']})")
                    
                    # لقطة شاشة للمساعدة في التصحيح
                    screenshot_b64 = ""
                    try:
                        screenshot = await page.screenshot(type='jpeg', quality=30, full_page=True)
                        screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
                        logs.append("📸 Screenshot captured")
                    except Exception as e:
                        logs.append(f"⚠️ Screenshot failed: {str(e)}")
                    
                    await browser.close()
                    
                    return {
                        "success": False,
                        "error": "No pure numeric URL files detected",
                        "logs": logs,
                        "total_responses": len(all_responses),
                        "numeric_responses": numeric_responses[:10],  # أول 10 فقط
                        "screenshot": screenshot_b64,
                        "all_responses_sample": all_responses[:20]  # أول 20 استجابة للتصحيح
                    }
                    
            except Exception as e:
                logs.append(f"❌ Page error: {str(e)}")
                
                # حتى مع الخطأ، حاول الحصول على الردود الملتقطة
                if numeric_responses:
                    logs.append(f"ℹ️ But found {len(numeric_responses)} numeric responses before error")
                
                try:
                    await browser.close()
                except:
                    pass
                
                return {
                    "success": False,
                    "error": f"Page error: {str(e)}",
                    "logs": logs,
                    "numeric_responses": numeric_responses,
                    "all_responses": all_responses
                }
                
    except Exception as e:
        return {
            "success": False,
            "error": f"Browser Error: {str(e)}",
            "trace": traceback.format_exc(),
            "logs": logs
        }

# ==============================================================================
# 👇 واجهة API محسنة مع خيارات أكثر مرونة 👇
# ==============================================================================
@app.get("/get-movie")
async def get_movie_api(
    request: Request, 
    response: Response,
    timeout: int = 10,
    wait: str = "load"
):
    debug_logs = []
    start_time = time.time()
    
    try:
        # قراءة الرابط
        raw_query_bytes = request.scope['query_string']
        raw_query_string = raw_query_bytes.decode("utf-8")
        
        debug_logs.append(f"🔍 Query received")
        debug_logs.append(f"⏱️ Timeout setting: {timeout}s")
        debug_logs.append(f"⏳ Wait mode: {wait}")
        
        if "url=" in raw_query_string:
            target_url = raw_query_string.split("url=", 1)[1]
            decoded_url = unquote(target_url)
            
            debug_logs.append(f"🎯 Target: {decoded_url[:150]}...")
            
            # تحديث إعدادات الوقت بناءً على المعاملات
            global_timeout = min(timeout, 30)  # حد أقصى 30 ثانية
            
            # إضافة إعدادات الوقت للدالة
            result = await scrape_movie_data(decoded_url, debug_logs)
            
            # حساب الوقت
            elapsed_time = time.time() - start_time
            debug_logs.append(f"⏱️ Total execution time: {elapsed_time:.2f} seconds")
            
            if isinstance(result, dict):
                result["processing_time"] = f"{elapsed_time:.2f}s"
                result["settings"] = {
                    "timeout": f"{timeout}s",
                    "wait_mode": wait
                }
            
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
# 👇 واجهة بديلة - جلب أي ملف بغض النظر عن النمط 👇
# ==============================================================================
@app.get("/scan-all")
async def scan_all_files(
    url: str,
    pattern: str = None,
    max_time: int = 15
):
    """مسح شامل لكل الملفات في الشبكة"""
    logs = []
    start_time = time.time()
    
    try:
        logs.append(f"🔍 Scanning all files from: {url[:200]}...")
        logs.append(f"⏱️ Max time: {max_time}s")
        
        if pattern:
            logs.append(f"🔎 Pattern filter: {pattern}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy={"server": WORKING_PROXY} if WORKING_PROXY else None,
                args=["--no-sandbox"],
                timeout=30000
            )
            
            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            page.set_default_timeout(max_time * 1000)
            
            # جمع كل الردود
            all_responses = []
            
            def collect_responses(response):
                try:
                    all_responses.append({
                        "url": response.url,
                        "status": response.status,
                        "type": response.request.resource_type,
                        "headers": dict(response.headers)
                    })
                except:
                    pass
            
            page.on("response", collect_responses)
            
            # تحميل الصفحة
            await page.goto(url, wait_until="load", timeout=10000)
            
            # انتظر وقت إضافي لجمع الردود
            await asyncio.sleep(5)
            
            # تصفية الردود المهمة
            video_responses = [r for r in all_responses if 
                              'video' in r['headers'].get('content-type', '').lower() or
                              'm3u8' in r['url'].lower() or
                              'mp4' in r['url'].lower() or
                              '.ts' in r['url'].lower()]
            
            json_responses = [r for r in all_responses if 
                             'application/json' in r['headers'].get('content-type', '').lower()]
            
            numeric_responses = [r for r in all_responses if 
                                re.search(r'/\d{6,}', r['url'])]
            
            await browser.close()
            
            elapsed = time.time() - start_time
            
            return {
                "success": True,
                "scan_time": f"{elapsed:.2f}s",
                "total_responses": len(all_responses),
                "video_files": len(video_responses),
                "json_files": len(json_responses),
                "numeric_files": len(numeric_responses),
                "video_urls": [r['url'] for r in video_responses[:10]],
                "json_urls": [r['url'] for r in json_responses[:10]],
                "numeric_urls": [r['url'] for r in numeric_responses[:10]],
                "all_responses_sample": all_responses[:50],
                "logs": logs
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "time": f"{time.time() - start_time:.2f}s",
            "logs": logs
        }

# ==============================================================================
# 👇 صفحة الواجهة الرئيسية 👇
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>Advanced Video File Scanner</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; max-width: 1200px; margin: 0 auto; }
                h1 { color: #333; }
                .container { background: #f5f5f5; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
                input, select { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; }
                button { background: #4CAF50; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }
                button:hover { background: #45a049; }
                .button-secondary { background: #008CBA; }
                .button-secondary:hover { background: #007B9A; }
                .tab { overflow: hidden; border: 1px solid #ccc; background-color: #f1f1f1; }
                .tab button { background-color: inherit; float: left; border: none; outline: none; cursor: pointer; padding: 14px 16px; transition: 0.3s; }
                .tab button:hover { background-color: #ddd; }
                .tab button.active { background-color: #ccc; }
                .tabcontent { display: none; padding: 20px; border: 1px solid #ccc; border-top: none; }
                .result { background: white; padding: 15px; margin: 10px 0; border-radius: 5px; border: 1px solid #ddd; }
                pre { background: #333; color: #fff; padding: 10px; border-radius: 5px; overflow-x: auto; max-height: 500px; overflow-y: auto; }
                .log-entry { font-family: monospace; font-size: 12px; margin: 2px 0; }
            </style>
        </head>
        <body>
            <h1>🎬 Advanced Video File Scanner</h1>
            
            <div class="tab">
                <button class="tablinks active" onclick="openTab(event, 'quick')">Quick Scan</button>
                <button class="tablinks" onclick="openTab(event, 'advanced')">Advanced Scan</button>
                <button class="tablinks" onclick="openTab(event, 'all')">Scan All Files</button>
            </div>
            
            <div id="quick" class="tabcontent" style="display: block;">
                <h3>Quick Numeric File Scan</h3>
                <p>Fast scan for numeric URL patterns (e.g., /123456789)</p>
                <input type="text" id="quickUrl" placeholder="https://example.com/movie-page" />
                <button onclick="quickScan()">🚀 Quick Scan</button>
                <div id="quickResult"></div>
            </div>
            
            <div id="advanced" class="tabcontent">
                <h3>Advanced Scan with Options</h3>
                <input type="text" id="advancedUrl" placeholder="Enter URL" />
                <div style="display: flex; gap: 10px;">
                    <div style="flex: 1;">
                        <label>Timeout (seconds):</label>
                        <select id="timeout">
                            <option value="5">5</option>
                            <option value="10" selected>10</option>
                            <option value="15">15</option>
                            <option value="20">20</option>
                        </select>
                    </div>
                    <div style="flex: 1;">
                        <label>Wait Mode:</label>
                        <select id="waitMode">
                            <option value="load">Load (fastest)</option>
                            <option value="domcontentloaded">DOM Ready</option>
                        </select>
                    </div>
                </div>
                <button onclick="advancedScan()">🔍 Advanced Scan</button>
                <div id="advancedResult"></div>
            </div>
            
            <div id="all" class="tabcontent">
                <h3>Scan All Network Files</h3>
                <p>Scan for all video, JSON, and numeric files</p>
                <input type="text" id="scanAllUrl" placeholder="Enter URL" />
                <button onclick="scanAll()">📡 Scan All Files</button>
                <div id="scanAllResult"></div>
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
                
                async function quickScan() {
                    const url = document.getElementById('quickUrl').value;
                    if (!url) { alert('Please enter URL'); return; }
                    
                    const resultDiv = document.getElementById('quickResult');
                    resultDiv.innerHTML = '<div class="result">⏳ Quick scanning...</div>';
                    
                    try {
                        const encoded = encodeURIComponent(url);
                        const response = await fetch(`/get-movie?url=${encoded}&timeout=8&wait=load`);
                        const data = await response.json();
                        
                        displayResult(resultDiv, data, 'Quick Scan');
                    } catch (error) {
                        resultDiv.innerHTML = `<div class="result">❌ Error: ${error.message}</div>`;
                    }
                }
                
                async function advancedScan() {
                    const url = document.getElementById('advancedUrl').value;
                    const timeout = document.getElementById('timeout').value;
                    const waitMode = document.getElementById('waitMode').value;
                    
                    if (!url) { alert('Please enter URL'); return; }
                    
                    const resultDiv = document.getElementById('advancedResult');
                    resultDiv.innerHTML = `<div class="result">⏳ Advanced scanning (timeout: ${timeout}s)...</div>`;
                    
                    try {
                        const encoded = encodeURIComponent(url);
                        const response = await fetch(`/get-movie?url=${encoded}&timeout=${timeout}&wait=${waitMode}`);
                        const data = await response.json();
                        
                        displayResult(resultDiv, data, 'Advanced Scan');
                    } catch (error) {
                        resultDiv.innerHTML = `<div class="result">❌ Error: ${error.message}</div>`;
                    }
                }
                
                async function scanAll() {
                    const url = document.getElementById('scanAllUrl').value;
                    if (!url) { alert('Please enter URL'); return; }
                    
                    const resultDiv = document.getElementById('scanAllResult');
                    resultDiv.innerHTML = '<div class="result">⏳ Scanning all network files...</div>';
                    
                    try {
                        const encoded = encodeURIComponent(url);
                        const response = await fetch(`/scan-all?url=${encoded}`);
                        const data = await response.json();
                        
                        let html = '<div class="result">';
                        if (data.success) {
                            html += `<h4>✅ Scan Complete!</h4>`;
                            html += `<p><strong>Time:</strong> ${data.scan_time}</p>`;
                            html += `<p><strong>Total Responses:</strong> ${data.total_responses}</p>`;
                            html += `<p><strong>Video Files:</strong> ${data.video_files}</p>`;
                            html += `<p><strong>JSON Files:</strong> ${data.json_files}</p>`;
                            html += `<p><strong>Numeric Files:</strong> ${data.numeric_files}</p>`;
                            
                            if (data.video_urls.length > 0) {
                                html += `<h5>Video URLs:</h5><ul>`;
                                data.video_urls.forEach(url => {
                                    html += `<li><a href="${url}" target="_blank">${url}</a></li>`;
                                });
                                html += `</ul>`;
                            }
                            
                            if (data.numeric_urls.length > 0) {
                                html += `<h5>Numeric URLs:</h5><ul>`;
                                data.numeric_urls.forEach(url => {
                                    html += `<li><a href="${url}" target="_blank">${url}</a></li>`;
                                });
                                html += `</ul>`;
                            }
                        } else {
                            html += `<h4>❌ Scan Failed</h4>`;
                            html += `<p><strong>Error:</strong> ${data.error}</p>`;
                        }
                        
                        html += `</div>`;
                        resultDiv.innerHTML = html;
                    } catch (error) {
                        resultDiv.innerHTML = `<div class="result">❌ Error: ${error.message}</div>`;
                    }
                }
                
                function displayResult(div, data, title) {
                    let html = `<div class="result"><h4>${title} Results</h4>`;
                    
                    if (data.success) {
                        html += `<p style="color: green;">✅ SUCCESS - Found target file!</p>`;
                        html += `<p><strong>Target URL:</strong> <a href="${data.target_url}" target="_blank">${data.target_url}</a></p>`;
                        html += `<p><strong>Content Type:</strong> ${data.content_type}</p>`;
                        html += `<p><strong>Time:</strong> ${data.processing_time}</p>`;
                        
                        if (data.content) {
                            html += `<h5>Content Preview:</h5>`;
                            html += `<pre>${JSON.stringify(data.content, null, 2).substring(0, 1500)}...</pre>`;
                        }
                    } else {
                        html += `<p style="color: red;">❌ FAILED - ${data.error}</p>`;
                        
                        if (data.numeric_responses && data.numeric_responses.length > 0) {
                            html += `<p><strong>Found ${data.numeric_responses.length} numeric patterns:</strong></p>`;
                            html += `<ul>`;
                            data.numeric_responses.forEach(resp => {
                                html += `<li><a href="${resp.url}" target="_blank">${resp.url.substring(0, 150)}...</a> (status: ${resp.status})</li>`;
                            });
                            html += `</ul>`;
                        }
                    }
                    
                    // عرض الـ logs
                    html += `<h5>Execution Logs:</h5><div style="background: #f0f0f0; padding: 10px; border-radius: 5px; max-height: 300px; overflow-y: auto;">`;
                    data.logs.forEach(log => {
                        const color = log.includes('✅') ? 'green' : 
                                     log.includes('❌') ? 'red' : 
                                     log.includes('⚠️') ? 'orange' : 
                                     log.includes('🎯') ? 'blue' : 'black';
                        html += `<div class="log-entry" style="color: ${color};">${log}</div>`;
                    });
                    html += `</div>`;
                    
                    html += `</div>`;
                    div.innerHTML = html;
                }
            </script>
        </body>
    </html>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
