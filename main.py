from fastapi import FastAPI, HTTPException, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os

app = FastAPI()

# لاحظ أننا أزلنا الرابط الثابت TARGET_LINK من هنا

def scrape_movie(target_url: str):
    print(f"🕵️‍♂️ Processing: {target_url}") # للتتبع في Logs
    movie_data = None
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()
        
        # حظر الموارد غير الضرورية
        page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "media", "font", "stylesheet"] else r.continue_())

        def handle_response(response):
            nonlocal movie_data
            # التحقق من الرابط والبيانات
            if "bnsi/movies" in response.url and response.status == 200:
                try:
                    data = response.json()
                    if "hlsSource" in data or "name" in data.get("data", {}):
                        movie_data = data
                except: pass

        page.on("response", handle_response)
        
        try:
            # نستخدم الرابط القادم من الطلب
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            try: page.mouse.click(500, 300)
            except: pass
            
            for _ in range(150): # انتظار 15 ثانية كحد أقصى
                if movie_data: break
                page.wait_for_timeout(100)
        except Exception as e:
            print(f"Error processing {target_url}: {e}")
        
        browser.close()

    return movie_data

@app.get("/")
def home():
    return {"status": "Active", "usage": "/get-movie?url=YOUR_LINK_HERE"}

@app.get("/get-movie")
def get_movie_api(url: str = Query(..., description="رابط الفيلم المراد جلبه")):
    # التحقق من وجود الرابط
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter is required")
        
    data = scrape_movie(url)
    
    if data:
        return data
    else:
        # يمكن إرجاع خطأ 404 أو JSON فارغ حسب رغبتك
        raise HTTPException(status_code=404, detail="Movie data not found or timeout")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
