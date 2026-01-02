from fastapi import FastAPI, HTTPException, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback
import time

app = FastAPI()

# ==============================================================================
# 🇷🇺 قائمة البروكسيات (Rotator)
# ضع هنا كل البروكسيات التي تجدها. الكود سيجربها واحداً تلو الآخر.
# ==============================================================================
PROXY_LIST = [
    "http://46.161.6.165:8080",       # بروكسي 1
    "http://176.126.103.194:44214",     # بروكسي 2
    "http://109.167.154.250:8080",  # بروكسي 3
    "http://79.133.183.196:8080",      # بروكسي 4
    "http://212.113.109.197:2080"       # بروكسي 5
]
# ==============================================================================

def scrape_with_proxy(target_url, proxy_address, logs):
    logs.append(f"🔄 Trying Proxy: {proxy_address} ...")
    movie_data = None
    
    with sync_playwright() as p:
        try:
            # تشغيل المتصفح
            browser = p.chromium.launch(
                headless=True,
                proxy={"server": proxy_address},
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
        except Exception as e:
            logs.append(f"❌ Failed to launch browser with {proxy_address}: {e}")
            return None, "Browser Launch Failed"

        try:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", timezone_id="Europe/Moscow"
            )
            # تقليل وقت الانتظار حتى لا نضيع وقتاً طويلاً على بروكسي ميت
            context.set_default_timeout(20000) # 20 ثانية لكل بروكسي
            
            page = context.new_page()
            
            # اعتراض البيانات
            def handle_response(response):
                nonlocal movie_data
                if "bnsi/movies" in response.url and response.status == 200:
                    try:
                        data = response.json()
                        movie_data = data
                    except: pass
            
            page.on("response", handle_response)
            
            # حظر الصور لتسريع التجربة
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "media", "font"] else r.continue_())

            logs.append(f"   --> Navigating to URL...")
            page.goto(target_url, wait_until="domcontentloaded")
            
            # التحقق من نجاح التحميل المبدئي
            title = page.title()
            logs.append(f"   --> Page Title: {title}")
            
            if "Access Denied" in title or not title:
                raise Exception("Blocked or Empty Title")

            # محاولة النقر
            try: page.mouse.click(500, 300)
            except: pass
            
            # انتظار سريع للبيانات
            for _ in range(50): # 5 ثواني
                if movie_data: break
                page.wait_for_timeout(100)
                
            browser.close()
            
            if movie_data:
                return movie_data, "Success"
            else:
                return None, "No Data Found"

        except Exception as e:
            logs.append(f"❌ Error with {proxy_address}: {str(e)}")
            browser.close()
            return None, str(e)

def scrape_manager(target_url):
    all_logs = []
    
    # 🔄 حلقة تكرارية لتجربة القائمة
    for proxy in PROXY_LIST:
        data, status = scrape_with_proxy(target_url, proxy, all_logs)
        if data:
            all_logs.append(f"✅ SUCCESS with proxy {proxy}!")
            return {"success": True, "data": data, "logs": all_logs}
        else:
            all_logs.append(f"⚠️ Failed with {proxy}, trying next...")
            
    return {"success": False, "diagnosis": "All Proxies Failed", "logs": all_logs}

@app.get("/")
def home():
    return {"status": "Active", "proxies_loaded": len(PROXY_LIST)}

@app.get("/get-movie")
def get_movie_api(url: str = Query(..., description="Movie URL")):
    return scrape_manager(url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
