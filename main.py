from fastapi import FastAPI, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback
import base64

app = FastAPI()

# البروكسي (تأكد أنه لا يزال حياً، إذا فشل جرب غيره)
WORKING_PROXY = "http://176.126.103.194:44214"

def scrape_movie_data(target_url: str):
    logs = []
    logs.append(f"🚀 Start: Connecting via {WORKING_PROXY}")
    
    movie_data = None
    snapshot = ""
    html_dump = ""
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=True,
                proxy={"server": WORKING_PROXY},
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            # إعداد سياق بمتصفح كامل
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", 
                timezone_id="Europe/Moscow"
            )
            context.set_default_timeout(60000) # 60 ثانية مهلة
            page = context.new_page()

            # المصيدة
            def handle_response(response):
                nonlocal movie_data
                # توسيع المصيدة لتشمل كل احتمالات ملفات الفيديو
                if response.status == 200 and ("bnsi/movies" in response.url or "master.m3u8" in response.url or "index.m3u8" in response.url):
                    try:
                        # إذا كان ملف JSON
                        if "application/json" in response.headers.get("content-type", ""):
                            data = response.json()
                            if "hlsSource" in data:
                                movie_data = data
                                logs.append("✅ JSON Data Captured!")
                        
                        # إذا كان ملف M3U8 مباشر
                        elif "m3u8" in response.url:
                             movie_data = {"direct_m3u8": response.url}
                             logs.append("✅ M3U8 Link Captured!")
                    except: pass

            page.on("response", handle_response)
            
            # حظر الصور لتسريع التحميل
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "font"] else r.continue_())

            try:
                logs.append("⏳ Loading Main Page...")
                # نفتح الرابط الأصلي الكامل (وليس المختصر)
                page.goto(target_url, wait_until="domcontentloaded")
                
                # 👇 الحل لمشكلة الشاشة البيضاء 👇
                logs.append("👀 Waiting for Player Iframe...")
                
                # ننتظر ظهور الـ iframe
                try:
                    iframe_element = page.wait_for_selector("iframe", timeout=30000)
                    if iframe_element:
                        logs.append("✅ Iframe Found! Entering...")
                        frame = iframe_element.content_frame()
                        
                        if frame:
                            # ننتظر قليلاً ثم نضغط داخل الإطار
                            page.wait_for_timeout(2000)
                            try:
                                # محاولة ضغط زر التشغيل داخل الإطار
                                frame.click("body", position={"x": 500, "y": 300}, force=True)
                                logs.append("🖱️ Clicked inside Iframe")
                            except:
                                logs.append("⚠️ Could not click inside frame (might be auto-play)")
                    else:
                        logs.append("⚠️ No Iframe found on page")
                        
                except Exception as e:
                    logs.append(f"⚠️ Iframe wait error: {str(e)}")

                # انتظار البيانات
                logs.append("⏳ Waiting for API response...")
                for _ in range(150):
                    if movie_data: break
                    page.wait_for_timeout(100)

            except Exception as e:
                logs.append(f"❌ Navigation Error: {str(e)}")

            # إذا فشل، نحفظ HTML لنفهم السبب
            if not movie_data:
                try:
                    html_dump = page.content()[:1000] # أول 1000 حرف
                    screenshot_bytes = page.screenshot(type='jpeg', quality=30)
                    snapshot = base64.b64encode(screenshot_bytes).decode('utf-8')
                except: pass

            browser.close()
            
            if movie_data:
                return movie_data
            else:
                return {
                    "success": False, 
                    "error": "Timeout", 
                    "logs": logs, 
                    "html_preview": html_dump, # سيخبرنا هل الصفحة محظورة
                    "screenshot_base64": snapshot
                }

        except Exception as e:
            return {"success": False, "error": str(e), "trace": traceback.format_exc()}

@app.get("/")
def home():
    return {"status": "Active"}

@app.get("/get-movie")
def get_movie_api(url: str = Query(..., description="Full URL")):
    return scrape_movie_data(url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
