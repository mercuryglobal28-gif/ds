from fastapi import FastAPI, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback

app = FastAPI()

def scrape_network_logs(target_url: str):
    # قوائم لتخزين البيانات المستخرجة
    js_files = []      # لتخزين ملفات الجافاسكربت
    all_requests = []  # لتخزين كل الطلبات الأخرى
    page_title = "Unknown"
    status_code = 0
    
    try:
        with sync_playwright() as p:
            print("1. Launching Browser (Direct Connection)...")
            
            # تشغيل المتصفح بدون بروكسي
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # 🕵️‍♂️ المصيدة: تسجيل كل طلب يخرج من المتصفح
            def handle_request(request):
                url = request.url
                resource_type = request.resource_type
                
                # تخزين الكل في القائمة العامة
                all_requests.append(f"[{resource_type}] {url}")
                
                # فرز ملفات JS
                if resource_type == "script" or ".js" in url:
                    js_files.append(url)
                    print(f"🔹 JS File Found: {url}")

            # تفعيل المصيدة
            page.on("request", handle_request)
            
            print(f"2. Navigating to: {target_url}")
            try:
                # محاولة فتح الصفحة
                response = page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                
                # جلب العنوان وحالة الطلب
                page_title = page.title()
                status_code = response.status if response else 0
                
                # انتظار قليل لتحميل السكربتات الإضافية
                page.wait_for_timeout(3000) 
                
            except Exception as e:
                print(f"⚠️ Navigation warning: {e}")
            
            browser.close()

            return {
                "success": True,
                "page_title": page_title,
                "status_code": status_code, # 403 يعني محظور، 200 يعني شغال
                "js_files_count": len(js_files),
                "js_files": js_files, # القائمة المطلوبة
                "other_requests_sample": all_requests[:10] # أول 10 طلبات عامة كعينة
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }

@app.get("/")
def home():
    return {"status": "Network Sniffer Active", "usage": "/analyze?url=..."}

@app.get("/analyze")
def analyze_page(url: str = Query(..., description="Target URL")):
    return scrape_network_logs(url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
