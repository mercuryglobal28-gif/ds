from fastapi import FastAPI, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback
from urllib.parse import urlparse, parse_qs

app = FastAPI()

# البروكسي الذي أثبت كفاءته
WORKING_PROXY = "http://176.126.103.194:44214"

def get_real_url(original_url: str):
    """
    وظيفة لاستخراج الرابط الحقيقي من داخل الرابط الطويل
    """
    try:
        parsed = urlparse(original_url)
        query_params = parse_qs(parsed.query)
        
        # هل يوجد باراميتر اسمه url؟ (مثل الرابط الذي تستخدمه)
        if "url" in query_params:
            real_url = query_params["url"][0]
            print(f"🎯 Smart Redirect: Found inner URL -> {real_url}")
            return real_url
        
        # هل الرابط هو أصلاً الرابط المباشر؟
        if "larkin" in original_url or "token_movie" in original_url:
            return original_url
            
    except:
        pass
    
    # إذا فشل الاستخراج، نستخدم الرابط الأصلي كما هو
    return original_url

def scrape_movie_data(input_url: str):
    logs = []
    
    # 1. استخراج الرابط المباشر (تجاوز الغلاف)
    target_url = get_real_url(input_url)
    
    logs.append(f"🚀 Start: Connecting to {target_url}")
    logs.append(f"🛡️ Proxy: {WORKING_PROXY}")
    
    movie_data = None
    
    with sync_playwright() as p:
        try:
            # تشغيل المتصفح
            browser = p.chromium.launch(
                headless=True,
                proxy={"server": WORKING_PROXY},
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            # إعداد السياق
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="ru-RU", timezone_id="Europe/Moscow"
            )
            context.set_default_timeout(60000)
            page = context.new_page()

            # 🕵️‍♂️ المصيدة
            def handle_response(response):
                nonlocal movie_data
                # توسيع نطاق البحث ليشمل balanser وكافة طلبات الـ API
                if ("bnsi/movies" in response.url or "cdn/movie" in response.url) and response.status == 200:
                    try:
                        data = response.json()
                        if "hlsSource" in data or "data" in data or "file" in data:
                            movie_data = data
                            logs.append("✅ Data Captured Successfully!")
                    except: pass

            page.on("response", handle_response)
            
            # حظر الصور والخطوط
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "font", "stylesheet"] else r.continue_())

            # 2. الذهاب للموقع
            logs.append("⏳ Navigating...")
            try:
                page.goto(target_url, wait_until="domcontentloaded")
                logs.append(f"📄 Title: {page.title()}")
                
                # 3. محاولة التشغيل (مهمة جداً للمواقع المباشرة)
                try: 
                    # نقرات في وسط الشاشة لتشغيل المشغل
                    page.mouse.click(500, 300)
                    page.wait_for_timeout(1000)
                    page.mouse.click(500, 300)
                except: pass
                
                # انتظار البيانات
                for _ in range(150): # 15 ثانية
                    if movie_data: break
                    page.wait_for_timeout(100)

            except Exception as e:
                logs.append(f"❌ Nav Error: {str(e)}")

            browser.close()
            
            if movie_data:
                return {"success": True, "data": movie_data}
            else:
                return {"success": False, "diagnosis": "Timeout - No JSON found", "logs": logs}

        except Exception as e:
            return {"success": False, "error": str(e), "logs": logs}

@app.get("/")
def home():
    return {"status": "Active", "mode": "Smart Redirect"}

@app.get("/get-movie")
def get_movie_api(url: str = Query(..., description="Full URL")):
    return scrape_movie_data(url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
