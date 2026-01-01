from fastapi import FastAPI, HTTPException, Query
from playwright.sync_api import sync_playwright
import uvicorn
import os
import traceback # مكتبة لتتبع تفاصيل الخطأ

app = FastAPI()

def scrape_movie(target_url: str):
    print(f"🚀 Starting scrape for: {target_url}")
    movie_data = None
    error_message = None
    
    try:
        with sync_playwright() as p:
            print("1. Launching browser...")
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
            
            # حظر الموارد
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "media", "font", "stylesheet"] else r.continue_())

            def handle_response(response):
                nonlocal movie_data
                if "bnsi/movies" in response.url and response.status == 200:
                    try:
                        data = response.json()
                        if "hlsSource" in data or "name" in data.get("data", {}):
                            movie_data = data
                            print("✅ Data caught!")
                    except: pass

            page.on("response", handle_response)
            
            print(f"2. Going to URL: {target_url}")
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"⚠️ Goto Error: {e}")
                raise e # نرفع الخطأ لنعرف السبب

            # محاولة النقر
            try: page.mouse.click(500, 300)
            except: pass
            
            print("3. Waiting for data...")
            for i in range(150):
                if movie_data: break
                page.wait_for_timeout(100)
            
            browser.close()
            
    except Exception as e:
        # هنا يتم تخزين الخطأ لعرضه لك
        error_message = str(e)
        traceback_str = traceback.format_exc()
        print(f"🔥 CRITICAL ERROR: {traceback_str}")
        return {"error": True, "message": error_message, "trace": traceback_str}

    return movie_data

@app.get("/")
def home():
    return {"status": "Active", "usage": "/get-movie?url=YOUR_LINK"}

@app.get("/get-movie")
def get_movie_api(url: str = Query(..., description="Movie URL")):
    if not url.startswith("http"):
        return {"error": True, "message": "Invalid URL. Must start with http or https"}
        
    result = scrape_movie(url)
    
    if result and "error" in result:
        # نعيد الخطأ كـ JSON بدلاً من 500 crash
        return result
    elif result:
        return result
    else:
        return {"error": True, "message": "No data found (Timeout)"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
