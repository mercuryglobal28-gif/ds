from fastapi import FastAPI, HTTPException, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback

app = FastAPI()

# ==========================================
# 🇷🇺 إعدادات البروكسي (تم دمج اختيارك هنا)
# ==========================================
PROXY_SERVER = "http://78.153.4.52:8080" 
PROXY_CONFIG = {"server": PROXY_SERVER}
# ==========================================

def scrape_movie(target_url: str):
    print(f"🚀 Processing via Proxy ({PROXY_SERVER}): {target_url}")
    movie_data = None
    
    try:
        with sync_playwright() as p:
            print("1. Launching browser with Proxy...")
            
            # تشغيل المتصفح مع إعدادات البروكسي
            browser = p.chromium.launch(
                headless=True,
                proxy=PROXY_CONFIG,  # 👈 هنا يتم تفعيل البروكسي
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            # إعداد السياق ليبدو كمتصفح حقيقي من روسيا
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU",
                timezone_id="Europe/Moscow"
            )
            page = context.new_page()
            
            # تسريع العملية بحظر الصور
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "media", "font"] else r.continue_())

            def handle_response(response):
                nonlocal movie_data
                if "bnsi/movies" in response.url and response.status == 200:
                    try:
                        data = response.json()
                        if "hlsSource" in data or "name" in data.get("data", {}):
                            movie_data = data
                            print("✅ Data caught successfully!")
                    except: pass

            page.on("response", handle_response)
            
            try:
                # محاولة فتح الرابط
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                
                # محاولة النقر لتفعيل الفيديو
                try: page.mouse.click(500, 300)
                except: pass
                
                # انتظار البيانات
                print("⏳ Waiting for movie data...")
                for _ in range(150): # 15 ثانية
                    if movie_data: break
                    page.wait_for_timeout(100)
                    
            except Exception as e:
                print(f"⚠️ Navigation/Proxy Error: {e}")
            
            browser.close()
            
    except Exception as e:
        return {"error": True, "message": str(e), "trace": traceback.format_exc()}

    return movie_data

@app.get("/")
def home():
    return {"status": "Running", "current_proxy": PROXY_SERVER}

@app.get("/get-movie")
def get_movie_api(url: str = Query(..., description="Movie URL")):
    result = scrape_movie(url)
    
    if result and not result.get("error"):
        return result
    else:
        # رسالة خطأ واضحة إذا فشل البروكسي
        error_msg = result.get("message") if result else "Timeout - No data found"
        return {
            "error": True, 
            "message": f"Failed via proxy {PROXY_SERVER}. Reason: {error_msg}",
            "tip": "Try changing the PROXY_SERVER IP in main.py"
        }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
