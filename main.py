from fastapi import FastAPI, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback
from urllib.parse import urlparse, parse_qs

app = FastAPI()

# ==============================================================================
# 🎯 البروكسي الذي يعمل (بناءً على فحوصاتنا السابقة)
# ==============================================================================
WORKING_PROXY = "http://176.126.103.194:44214"
# ==============================================================================

def get_real_url(original_url: str):
    """
    وظيفة مساعدة: تستخرج الرابط الحقيقي من الرابط الطويل لتسريع العملية
    """
    try:
        if "url=" in original_url:
            parsed = urlparse(original_url)
            query_params = parse_qs(parsed.query)
            if "url" in query_params:
                return query_params["url"][0]
    except: pass
    return original_url

def scrape_movie_data(input_url: str):
    # 1. تجهيز الرابط المباشر
    target_url = get_real_url(input_url)
    
    logs = [] # لتسجيل الأحداث في حال الخطأ
    logs.append(f"🚀 Start: Connecting via {WORKING_PROXY}")
    logs.append(f"🔗 Target: {target_url}")
    
    movie_data = None
    
    with sync_playwright() as p:
        try:
            # 2. تشغيل المتصفح مع البروكسي
            browser = p.chromium.launch(
                headless=True,
                proxy={"server": WORKING_PROXY},
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            # 3. إعداد السياق (روسيا)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ru-RU", 
                timezone_id="Europe/Moscow"
            )
            # زيادة وقت الانتظار لأن البروكسي قد يكون بطيئاً
            context.set_default_timeout(60000) 
            page = context.new_page()

            # 4. المصيدة (نفس المنطق في كودك المحلي)
            def handle_response(response):
                nonlocal movie_data
                # نبحث عن bnsi/movies أو أي ملف JSON يحتوي على hlsSource
                if ("bnsi/movies" in response.url or "cdn/movie" in response.url) and response.status == 200:
                    try:
                        data = response.json()
                        if "hlsSource" in data or "name" in data.get("data", {}):
                            movie_data = data
                            logs.append("✅ Data Captured!")
                    except: pass

            page.on("response", handle_response)
            
            # تسريع التصفح بحظر الصور
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "media", "font"] else r.continue_())

            # 5. الذهاب للموقع
            try:
                page.goto(target_url, wait_until="domcontentloaded")
                
                # التحقق من الحظر
                if "Access Denied" in page.title():
                     return {"success": False, "error": "Proxy Blocked (403)", "logs": logs}

                # 6. محاكاة النقرات (من كودك الأصلي)
                try: 
                    page.mouse.click(500, 300)
                    page.wait_for_timeout(1000)
                    page.mouse.click(500, 300)
                except: pass
                
                # انتظار البيانات
                for _ in range(200): # انتظار حتى 20 ثانية
                    if movie_data: break
                    page.wait_for_timeout(100)

            except Exception as e:
                logs.append(f"❌ Navigation Error: {str(e)}")

            browser.close()
            
            # 7. إرجاع النتيجة
            if movie_data:
                # تنظيف البيانات (اختياري) لتقليل حجم الرد
                return movie_data
            else:
                return {"success": False, "error": "Timeout - No Data Found", "logs": logs}

        except Exception as e:
            return {"success": False, "error": "Server/Browser Error", "details": str(e), "trace": traceback.format_exc()}

@app.get("/")
def home():
    return {"status": "Active", "proxy": WORKING_PROXY}

@app.get("/get-movie")
def get_movie_api(url: str = Query(..., description="Full Movie URL")):
    return scrape_movie_data(url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
