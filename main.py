from fastapi import FastAPI, HTTPException
from playwright.sync_api import sync_playwright
import uvicorn
import os

app = FastAPI()

# الرابط المستهدف
TARGET_LINK = "https://mercuryglobal28-gif.github.io/m/ind.html?url=https://larkin-as.stloadi.live/?token_movie=eeb7953c4ce7142d70e048cd71dce2&translation=66&token=d317441359e505c343c2063edc97e7"

def scrape_movie():
    movie_data = None
    with sync_playwright() as p:
        # إعدادات خاصة للسيرفر (Linux/Docker)
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", # مهم جداً للذاكرة المحدودة في Render
                "--disable-blink-features=AutomationControlled"
            ]
        )
        page = browser.new_page()
        
        # حظر الموارد الثقيلة لتوفير الرام
        page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "media", "font", "stylesheet"] else r.continue_())

        def handle_response(response):
            nonlocal movie_data
            if "bnsi/movies" in response.url and response.status == 200:
                try:
                    data = response.json()
                    if "hlsSource" in data or "name" in data.get("data", {}):
                        movie_data = data
                except: pass

        page.on("response", handle_response)
        
        try:
            # زيادة وقت الانتظار لأن السيرفر المجاني قد يكون بطيئاً
            page.goto(TARGET_LINK, wait_until="domcontentloaded", timeout=90000)
            try: page.mouse.click(500, 300)
            except: pass
            
            for _ in range(200): # انتظار حتى 20 ثانية
                if movie_data: break
                page.wait_for_timeout(100)
        except Exception as e:
            print(f"Error: {e}")
        
        browser.close()

    return movie_data

@app.get("/")
def home():
    return {"status": "Active", "msg": "Use /get-movie endpoint"}

@app.get("/get-movie")
def get_movie_api():
    data = scrape_movie()
    if data:
        return data
    else:
        raise HTTPException(status_code=500, detail="Failed to fetch data")

if __name__ == "__main__":
    # Render يحدد المنفذ تلقائياً عبر متغير بيئة PORT
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)