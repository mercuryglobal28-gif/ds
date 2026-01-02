from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from playwright.async_api import async_playwright
import uvicorn
import os
import traceback
import base64
import asyncio
from urllib.parse import unquote, urlparse, parse_qs, urlencode
import time
import re

app = FastAPI()

# البروكسي المعتمد
WORKING_PROXY = "http://176.126.103.194:44214"

async def find_bnsi_movie_deep(url: str, debug_logs: list):
    """بحث عميق عن ملفات bnsi/movies"""
    logs = debug_logs
    logs.append(f"🔍 Deep search started for: {url}")
    
    try:
        async with async_playwright() as p:
            # إعداد المتصفح مع تفعيل الـ proxy
            browser = await p.chromium.launch(
                headless=True,
                proxy={"server": WORKING_PROXY} if WORKING_PROXY else None,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--allow-running-insecure-content",
                ],
                timeout=30000
            )
            
            # إنشاء context مع إعدادات متساهلة
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                viewport={"width": 1920, "height": 1080},
                java_script_enabled=True,
                ignore_https_errors=True,
                bypass_csp=True
            )
            
            page = await context.new_page()
            page.set_default_timeout(15000)
            
            # تخزين جميع الـ responses
            all_responses = []
            target_responses = []
            
            # 1. جمع جميع الـ responses التي تحتوي على bnsi
            page.on("response", lambda response: all_responses.append(response))
            
            logs.append("🌐 Navigating to URL...")
            
            try:
                # الانتقال إلى الصفحة
                main_response = await page.goto(url, wait_until="networkidle", timeout=15000)
                if main_response:
                    logs.append(f"📄 Main page loaded: {main_response.status}")
            except Exception as e:
                logs.append(f"⚠️ Navigation warning: {str(e)}")
            
            # انتظار قصير
            await asyncio.sleep(3)
            
            # 2. البحث في iframes
            logs.append("🔎 Checking for iframes...")
            iframes = await page.query_selector_all("iframe")
            logs.append(f"Found {len(iframes)} iframes")
            
            for i, iframe in enumerate(iframes):
                try:
                    frame_src = await iframe.get_attribute("src")
                    if frame_src:
                        logs.append(f"  Iframe {i+1}: {frame_src}")
                        
                        # إذا كان الـ iframe يحتوي على stloadi، فاذهب إليه مباشرة
                        if "stloadi.live" in frame_src:
                            logs.append(f"  🎯 Found stloadi iframe, navigating...")
                            await page.goto(frame_src, wait_until="networkidle", timeout=10000)
                            await asyncio.sleep(2)
                except:
                    pass
            
            # 3. البحث في محتوى الصفحة عن روابط bnsi
            logs.append("🔍 Searching page content for bnsi patterns...")
            page_content = await page.content()
            
            # البحث عن أنماط مختلفة لـ bnsi
            bnsi_patterns = re.findall(r'(https?://[^"\']+?/bnsi/movies/\d+)', page_content)
            if bnsi_patterns:
                logs.append(f"✅ Found {len(bnsi_patterns)} bnsi URLs in page source")
                for pattern in bnsi_patterns[:3]:  # أول 3 فقط
                    logs.append(f"  📍 {pattern}")
                    
                    # محاولة الوصول إلى الرابط مباشرة
                    try:
                        logs.append(f"  🔗 Attempting direct access...")
                        direct_response = await page.goto(pattern, wait_until="networkidle", timeout=10000)
                        
                        if direct_response:
                            # محاولة الحصول على المحتوى
                            try:
                                content = await direct_response.text()
                                logs.append(f"  📊 Direct access successful: {len(content)} chars")
                                
                                # تحقق إذا كان JSON
                                try:
                                    json_data = await direct_response.json()
                                    return {
                                        "success": True,
                                        "found": True,
                                        "type": "direct_json",
                                        "url": pattern,
                                        "data": json_data,
                                        "source": "direct_url_in_page"
                                    }
                                except:
                                    # إذا لم يكن JSON، أرجع جزء من النص
                                    return {
                                        "success": True,
                                        "found": True,
                                        "type": "direct_text",
                                        "url": pattern,
                                        "data_preview": content[:1000],
                                        "full_length": len(content),
                                        "source": "direct_url_in_page"
                                    }
                            except:
                                pass
                    except Exception as e:
                        logs.append(f"  ❌ Direct access failed: {str(e)}")
            
            # 4. تحليل الـ responses المجمعة
            logs.append(f"📊 Analyzing {len(all_responses)} collected responses...")
            
            for i, response in enumerate(all_responses):
                try:
                    response_url = response.url
                    
                    # البحث عن bnsi في الـ URLs
                    if "/bnsi/movies/" in response_url:
                        logs.append(f"🎯 Found bnsi response #{i+1}: {response_url}")
                        
                        # محاولة الحصول على المحتوى
                        try:
                            # أولاً كـ JSON
                            json_data = await response.json()
                            logs.append(f"  ✅ JSON data captured: {len(str(json_data))} chars")
                            
                            await browser.close()
                            return {
                                "success": True,
                                "found": True,
                                "type": "response_json",
                                "url": response_url,
                                "data": json_data,
                                "response_index": i+1
                            }
                            
                        except:
                            # إذا لم يكن JSON، حاول كـ نص
                            try:
                                text = await response.text()
                                logs.append(f"  📄 Text data captured: {len(text)} chars")
                                
                                await browser.close()
                                return {
                                    "success": True,
                                    "found": True,
                                    "type": "response_text",
                                    "url": response_url,
                                    "data_preview": text[:1000],
                                    "full_length": len(text),
                                    "response_index": i+1
                                }
                            except Exception as e:
                                logs.append(f"  ⚠️ Could not read response: {str(e)}")
                                
                except Exception as e:
                    continue
            
            # 5. محاولة تنفيذ JavaScript للعثور على الروابط
            logs.append("🤖 Executing JavaScript to find movie data...")
            
            try:
                # البحث عن عناصر الفيديو والمشغلات
                js_result = await page.evaluate("""
                    () => {
                        const results = {
                            videos: [],
                            iframes: [],
                            scripts: [],
                            network_requests: []
                        };
                        
                        // البحث عن فيديوهات
                        document.querySelectorAll('video').forEach(video => {
                            if (video.src) results.videos.push(video.src);
                            video.querySelectorAll('source').forEach(source => {
                                if (source.src) results.videos.push(source.src);
                            });
                        });
                        
                        // البحث عن iframes
                        document.querySelectorAll('iframe').forEach(iframe => {
                            if (iframe.src) results.iframes.push(iframe.src);
                        });
                        
                        // البحث عن scripts تحتوي على bnsi
                        document.querySelectorAll('script').forEach(script => {
                            if (script.src && script.src.includes('bnsi')) {
                                results.scripts.push(script.src);
                            }
                            if (script.textContent && script.textContent.includes('bnsi')) {
                                results.scripts.push('inline: ' + script.textContent.substring(0, 200));
                            }
                        });
                        
                        // محاولة الحصول على طلبات الشبكة من window
                        if (window.performance && window.performance.getEntriesByType) {
                            window.performance.getEntriesByType('resource').forEach(resource => {
                                if (resource.name.includes('bnsi')) {
                                    results.network_requests.push(resource.name);
                                }
                            });
                        }
                        
                        return results;
                    }
                """)
                
                logs.append(f"🤖 JS found: {len(js_result['videos'])} videos, {len(js_result['iframes'])} iframes")
                
                # التحقق مما إذا وجدنا شيء مفيد
                if js_result['scripts']:
                    logs.append(f"📜 Found {len(js_result['scripts'])} scripts with bnsi")
                    for script in js_result['scripts'][:2]:
                        logs.append(f"  📝 {script[:100]}...")
                        
                if js_result['network_requests']:
                    logs.append(f"🌐 Found {len(js_result['network_requests'])} network requests")
                    for req in js_result['network_requests'][:2]:
                        logs.append(f"  🔗 {req}")
                        
            except Exception as e:
                logs.append(f"⚠️ JavaScript execution failed: {str(e)}")
            
            # 6. أخذ لقطة شاشة للتصحيح
            logs.append("📸 Taking screenshot for debugging...")
            try:
                screenshot = await page.screenshot(type='jpeg', quality=40)
                screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
                logs.append("✅ Screenshot captured")
            except Exception as e:
                screenshot_b64 = ""
                logs.append(f"❌ Screenshot failed: {str(e)}")
            
            await browser.close()
            
            # 7. إذا لم نجد شيئاً، نعيد معلومات التصحيح
            return {
                "success": False,
                "found": False,
                "message": "Could not find bnsi/movies file despite deep search",
                "debug_info": {
                    "total_responses": len(all_responses),
                    "page_size": len(page_content),
                    "iframes_found": len(iframes),
                    "bnsi_patterns_in_source": len(bnsi_patterns),
                    "screenshot_available": bool(screenshot_b64)
                },
                "logs": logs,
                "screenshot_base64": screenshot_b64[:50000] if screenshot_b64 else ""  # جزء فقط لتجنب حجم كبير
            }
            
    except Exception as e:
        logs.append(f"❌ Critical error: {str(e)}")
        return {
            "success": False,
            "found": False,
            "error": str(e),
            "trace": traceback.format_exc(),
            "logs": logs
        }

async def extract_movie_from_token_url(token_url: str, debug_logs: list):
    """محاولة استخراج فيديو مباشرة من رابط token"""
    logs = debug_logs
    logs.append(f"🎯 Attempting direct token extraction: {token_url}")
    
    try:
        # تحليل الرابط
        parsed = urlparse(token_url)
        query_params = parse_qs(parsed.query)
        
        # البحث عن token_movie أو token
        movie_token = None
        if 'token_movie' in query_params:
            movie_token = query_params['token_movie'][0]
        elif 'token' in query_params:
            movie_token = query_params['token'][0]
        
        if movie_token:
            logs.append(f"🔑 Found movie token: {movie_token}")
            
            # محاولة إنشاء رابط bnsi محتمل
            # هذا يعتمد على بنية الموقع
            possible_bnsi_urls = [
                f"https://harald-as.stloadi.live/bnsi/movies/{movie_token}",
                f"https://harald-as.stloadi.live/bnsi/movies/224656",  # مثال
                f"https://larkin-as.stloadi.live/bnsi/movies/{movie_token}",
                f"https://larkin-as.stloadi.live/bnsi/movies/224656",
            ]
            
            # جرب كل رابط
            for test_url in possible_bnsi_urls:
                logs.append(f"🔗 Testing possible URL: {test_url}")
                
                try:
                    async with async_playwright() as p:
                        browser = await p.chromium.launch(
                            headless=True,
                            proxy={"server": WORKING_PROXY} if WORKING_PROXY else None,
                            args=["--no-sandbox"],
                            timeout=10000
                        )
                        
                        page = await browser.new_page()
                        page.set_default_timeout(7000)
                        
                        response = await page.goto(test_url, wait_until="networkidle", timeout=7000)
                        
                        if response and response.status == 200:
                            try:
                                json_data = await response.json()
                                await browser.close()
                                
                                return {
                                    "success": True,
                                    "found": True,
                                    "type": "direct_token_url",
                                    "original_token": movie_token,
                                    "url": test_url,
                                    "data": json_data
                                }
                            except:
                                try:
                                    text = await response.text()
                                    await browser.close()
                                    
                                    return {
                                        "success": True,
                                        "found": True,
                                        "type": "direct_token_text",
                                        "original_token": movie_token,
                                        "url": test_url,
                                        "data_preview": text[:1000]
                                    }
                                except:
                                    pass
                        
                        await browser.close()
                        
                except Exception as e:
                    logs.append(f"  ⚠️ Test failed: {str(e)}")
                    continue
        
        return {"success": False, "message": "Could not extract from token"}
        
    except Exception as e:
        logs.append(f"❌ Token extraction error: {str(e)}")
        return {"success": False, "error": str(e)}

# ==============================================================================
# واجهات API
# ==============================================================================
@app.get("/deep-find-bnsi")
async def deep_find_bnsi(request: Request):
    """واجهة البحث العميق"""
    debug_logs = []
    start_time = time.time()
    
    try:
        # استخراج الـ URL من query string
        query_string = request.scope['query_string'].decode("utf-8")
        if "url=" not in query_string:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing url parameter"}
            )
        
        target_url = unquote(query_string.split("url=", 1)[1])
        debug_logs.append(f"🎯 Target URL: {target_url}")
        
        # 1. أولاً: حاول استخراج من token إذا كان موجوداً
        if "token_movie" in target_url or "token=" in target_url:
            token_result = await extract_movie_from_token_url(target_url, debug_logs)
            if token_result.get("success") and token_result.get("found"):
                debug_logs.append("✅ Found via token extraction!")
                return token_result
        
        # 2. ثانياً: البحث العميق في الصفحة
        debug_logs.append("🔍 Starting deep page analysis...")
        result = await find_bnsi_movie_deep(target_url, debug_logs)
        
        # إضافة وقت المعالجة
        elapsed = time.time() - start_time
        result["processing_time"] = f"{elapsed:.2f}s"
        
        return result
        
    except Exception as e:
        debug_logs.append(f"❌ API Error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc(),
            "logs": debug_logs,
            "processing_time": f"{time.time() - start_time:.2f}s"
        }

@app.get("/direct-bnsi-test")
async def direct_bnsi_test(movie_id: str = "224656"):
    """اختبار مباشر لرابط bnsi"""
    start_time = time.time()
    logs = []
    
    # قائمة مجالات محتملة
    domains = [
        "harald-as.stloadi.live",
        "larkin-as.stloadi.live", 
        "mercury-as.stloadi.live",
        "stloadi.live"
    ]
    
    for domain in domains:
        test_url = f"https://{domain}/bnsi/movies/{movie_id}"
        logs.append(f"🔗 Testing: {test_url}")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    proxy={"server": WORKING_PROXY} if WORKING_PROXY else None,
                    args=["--no-sandbox"],
                    timeout=10000
                )
                
                page = await browser.new_page()
                response = await page.goto(test_url, wait_until="networkidle", timeout=8000)
                
                if response and response.status == 200:
                    try:
                        json_data = await response.json()
                        await browser.close()
                        
                        return {
                            "success": True,
                            "found": True,
                            "domain": domain,
                            "url": test_url,
                            "data": json_data,
                            "time": f"{time.time() - start_time:.2f}s"
                        }
                    except:
                        try:
                            text = await response.text()
                            await browser.close()
                            
                            return {
                                "success": True,
                                "found": True,
                                "domain": domain,
                                "url": test_url,
                                "data_type": "text",
                                "content_preview": text[:500],
                                "time": f"{time.time() - start_time:.2f}s"
                            }
                        except:
                            pass
                
                await browser.close()
                
        except Exception as e:
            logs.append(f"  ❌ Failed: {str(e)}")
            continue
    
    return {
        "success": False,
        "message": "No direct bnsi access worked",
        "logs": logs,
        "time": f"{time.time() - start_time:.2f}s"
    }

# الصفحة الرئيسية
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>Enhanced BNSI Movie Finder</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; background: #f0f2f5; }
                .container { max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 20px rgba(0,0,0,0.1); }
                h1 { color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }
                .method { background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0; border-left: 4px solid #007bff; }
                .url-input { width: 95%; padding: 12px; font-size: 16px; border: 2px solid #ddd; border-radius: 5px; margin: 10px 0; font-family: monospace; }
                button { padding: 12px 25px; margin: 5px; font-size: 16px; border: none; border-radius: 5px; cursor: pointer; }
                .btn-primary { background: #007bff; color: white; }
                .btn-success { background: #28a745; color: white; }
                .btn-warning { background: #ffc107; color: black; }
                #result { margin-top: 30px; padding: 20px; background: #f8f9fa; border-radius: 5px; display: none; }
                .log-entry { padding: 5px 10px; margin: 2px 0; background: white; border-left: 3px solid #6c757d; font-family: monospace; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎬 Enhanced BNSI Movie Finder</h1>
                <p>Advanced tool to find and extract <code>/bnsi/movies/</code> files</p>
                
                <div class="method">
                    <h3>🔍 Method 1: Deep Analysis</h3>
                    <p>Analyzes page content, iframes, scripts, and network requests</p>
                    <input type="text" class="url-input" id="deepUrl" 
                           placeholder="Paste full URL here (e.g., https://mercuryglobal28-gif.github.io/m/ind.html?url=...)">
                    <br>
                    <button class="btn-primary" onclick="deepSearch()">Deep Analysis Search</button>
                </div>
                
                <div class="method">
                    <h3>⚡ Method 2: Direct BNSI Test</h3>
                    <p>Tests direct access to common bnsi domains</p>
                    <input type="text" class="url-input" id="movieId" placeholder="Movie ID (e.g., 224656)" value="224656">
                    <br>
                    <button class="btn-success" onclick="directTest()">Test Direct Access</button>
                </div>
                
                <div class="method">
                    <h3>🎯 Method 3: Token Extraction</h3>
                    <p>Extracts movie token and tries to construct bnsi URL</p>
                    <button class="btn-warning" onclick="testToken()">Test Token Extraction</button>
                </div>
                
                <div id="result">
                    <h3>Results:</h3>
                    <div id="resultContent"></div>
                    <h4>Logs:</h4>
                    <div id="logsContainer"></div>
                </div>
            </div>
            
            <script>
                function deepSearch() {
                    const url = document.getElementById("deepUrl").value;
                    if (!url) {
                        alert("Please enter a URL");
                        return;
                    }
                    
                    const encodedUrl = encodeURIComponent(url);
                    showLoading("Deep analysis in progress...");
                    
                    fetch(`/deep-find-bnsi?url=${encodedUrl}`)
                        .then(r => r.json())
                        .then(displayResult)
                        .catch(err => {
                            document.getElementById("resultContent").innerHTML = `<p style="color: red">Error: ${err}</p>`;
                            document.getElementById("result").style.display = 'block';
                        });
                }
                
                function directTest() {
                    const movieId = document.getElementById("movieId").value || "224656";
                    showLoading(`Testing direct access for ID: ${movieId}`);
                    
                    fetch(`/direct-bnsi-test?movie_id=${movieId}`)
                        .then(r => r.json())
                        .then(displayResult)
                        .catch(err => {
                            document.getElementById("resultContent").innerHTML = `<p style="color: red">Error: ${err}</p>`;
                            document.getElementById("result").style.display = 'block';
                        });
                }
                
                function testToken() {
                    const sampleUrl = "https://mercuryglobal28-gif.github.io/m/ind.html?url=https://harald-as.stloadi.live/?token_movie=c1e0e2f4b897656d8566e5da785eb1&translation=93&token=e7b61f129f4a392ac4bf6726a9dd6a";
                    document.getElementById("deepUrl").value = sampleUrl;
                    deepSearch();
                }
                
                function showLoading(message) {
                    document.getElementById("result").style.display = 'block';
                    document.getElementById("resultContent").innerHTML = `<p>⏳ ${message}</p>`;
                    document.getElementById("logsContainer").innerHTML = '';
                }
                
                function displayResult(data) {
                    const resultDiv = document.getElementById("resultContent");
                    const logsDiv = document.getElementById("logsContainer");
                    
                    // عرض النتيجة الرئيسية
                    let html = `<div style="background: ${data.success ? '#d4edda' : '#f8d7da'}; padding: 15px; border-radius: 5px;">`;
                    html += `<h4>${data.success ? '✅ SUCCESS' : '❌ FAILED'}</h4>`;
                    html += `<p><strong>Message:</strong> ${data.message || 'No message'}</p>`;
                    
                    if (data.found) {
                        html += `<p><strong>Type:</strong> ${data.type}</p>`;
                        html += `<p><strong>URL:</strong> ${data.url || 'N/A'}</p>`;
                        
                        if (data.data) {
                            html += `<p><strong>Data Preview:</strong></p>`;
                            html += `<pre style="background: white; padding: 10px; overflow: auto; max-height: 300px;">${JSON.stringify(data.data, null, 2)}</pre>`;
                        }
                    }
                    
                    html += `<p><strong>Processing Time:</strong> ${data.processing_time || data.time || 'N/A'}</p>`;
                    html += `</div>`;
                    
                    resultDiv.innerHTML = html;
                    
                    // عرض الـ logs
                    if (data.logs && data.logs.length > 0) {
                        let logsHtml = '';
                        data.logs.forEach(log => {
                            logsHtml += `<div class="log-entry">${log}</div>`;
                        });
                        logsDiv.innerHTML = logsHtml;
                    }
                    
                    document.getElementById("result").style.display = 'block';
                }
            </script>
        </body>
    </html>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
