from fastapi import FastAPI, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os
import base64

app = FastAPI()

# البروكسي الذي نجح معك في Curl
WORKING_PROXY = "http://176.126.103.194:44214"

def debug_scrape(target_url: str):
    logs = []
    snapshot = "No Screenshot"
    html_content = "No HTML"
    
    logs.append(f"🚀 Start: Connecting via {WORKING_PROXY}")
    
    with sync_playwright() as p:
        try:
            # تشغيل المتصفح
            browser = p.chromium.launch(
                headless=True,
                proxy={"server": WORKING_PROXY},
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled" # محاولة إخفاء الروبوت
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # 1. اختبار البروكسي: هل نحن في روسيا حقاً؟
            logs.append("🕵️ Checking IP address inside browser...")
            try:
                page.goto("http://ifconfig.me", timeout=30000)
                current_ip = page.content()
                logs.append(f"✅ IP visible to browser: {current_ip[:50]}...") # نعرض أول 50 حرف
            except Exception as e:
                logs.append(f"⚠️ Could not verify IP: {str(e)}")

            # 2. الذهاب للموقع المستهدف
            logs.append(f"⏳ Navigating to Target URL...")
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                
                # جلب العنوان
                title = page.title()
                logs.append(f"📄 Page Title: '{title}'")
                
                # جلب جزء من محتوى الصفحة لنعرف ما هي
                content = page.content()
                html_content = content[:500] # أول 500 حرف من الكود المصدري
                
                # 📸 التقاط صورة للمشكلة
                screenshot_bytes = page.screenshot(type='jpeg', quality=50)
                snapshot = base64.b64encode(screenshot_bytes).decode('utf-8')
                logs.append("📸 Screenshot captured!")

            except Exception as e:
                logs.append(f"❌ Navigation Failed: {str(e)}")
            
            browser.close()
            
            return {
                "logs": logs,
                "html_preview": html_content,
                "screenshot_base64": snapshot # انسخ هذا وضعه في موقع لتحويله لصورة
            }

        except Exception as e:
            return {"error": str(e), "logs": logs}

@app.get("/get-movie")
def get_movie_api(url: str = Query(..., description="Target URL")):
    return debug_scrape(url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
