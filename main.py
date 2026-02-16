import os
import json
import time
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# ==============================================================================
# ⚙️ الإعدادات
# ==============================================================================
PROXY_SERVER = os.getenv("PROXY_SERVER", "46.161.47.123:9771")
PROXY_USER = os.getenv("PROXY_USER", "oFRHax")
PROXY_PASS = os.getenv("PROXY_PASS", "4yFtU8")
BASE_URL = "https://kinovod120226.pro"

# ==============================================================================
# 🕵️‍♂️ منطق "المحقق" (Logging Everything)
# ==============================================================================
def diagnostic_intercept(route, request):
    url = request.url.lower()
    rt = request.resource_type
    
    # تسجيل ما يتم حظره للتأكد أننا لا نحظر مشغل الفيديو بالخطأ
    if rt in ["image", "font", "stylesheet"]:
        # نحظر هذه الأشياء عادة، لكن لن نسجلها لعدم الإزعاج
        return route.abort()
    
    if rt == "script":
        # تسجيل السكربتات المحظورة والمقبولة
        if "kinovod" in url or "hs.js" in url or "jquery" in url:
            return route.continue_()
        elif "player" in url or "bundle" in url:
            print(f"⚠️ انتباه: تم حظر سكربت قد يكون مهماً: {url}", flush=True)
            return route.abort()
        else:
            return route.abort()

    # تسجيل أي طلب XHR أو Fetch (غالباً البيانات تكون هنا)
    if rt in ["xhr", "fetch"]:
        print(f"📡 طلب شبكة: {url}", flush=True)

    route.continue_()

def run_diagnostic(query_text):
    print(f"\n{'='*40}\n🔍 بدء التشخيص لـ: {query_text}\n{'='*40}", flush=True)
    
    logs = []
    
    with sync_playwright() as p:
        try:
            print("🔄 تشغيل المتصفح...", flush=True)
            browser = p.chromium.launch(
                headless=True,
                proxy={
                    "server": f"http://{PROXY_SERVER}",
                    "username": PROXY_USER,
                    "password": PROXY_PASS
                },
                args=["--no-sandbox", "--disable-gpu", "--blink-settings=imagesEnabled=false"]
            )
            
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            
            # تفعيل الاستماع للشبكة
            page.route("**/*", diagnostic_intercept)

            # ---------------------------------------------------------
            # 🕵️‍♂️ جاسوس JSON "الثرثار" (يسجل كل شيء)
            # ---------------------------------------------------------
            spy_script = """
            const originalParse = JSON.parse;
            JSON.parse = function(text, reviver) {
                try {
                    const result = originalParse(text, reviver);
                    // تسجيل أي JSON يحتوي على كلمات مفتاحية
                    const str = JSON.stringify(result);
                    if (str.includes('mp4') || str.includes('m3u8') || str.includes('file') || str.includes('player')) {
                        console.log('$$$POSSIBLE_DATA$$$ ' + str.substring(0, 500)); // نطبع أول 500 حرف فقط
                    } else {
                        console.log('$$$JSON_IGNORE$$$ ' + str.substring(0, 50));
                    }
                    return result;
                } catch (e) { return originalParse(text, reviver); }
            }
            """
            page.add_init_script(spy_script)

            page.on("console", lambda msg: print(f"🖥️ Browser Log: {msg.text}", flush=True) if "$$$" in msg.text else None)

            # 1. البحث
            search_url = f"{BASE_URL}/search?query={query_text}"
            print(f"🌍 الذهاب للبحث: {search_url}", flush=True)
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")

            # العثور على الرابط
            try:
                element = page.query_selector("a[href*='/serial/'], a[href*='/film/']")
                if not element:
                    print("❌ لم يتم العثور على نتائج بحث.", flush=True)
                    return {"status": "No results found"}
                
                href = element.get_attribute("href")
                target_url = BASE_URL + href
                print(f"✅ تم العثور على: {target_url}", flush=True)
                
                # التحقق هل هو فيلم أم مسلسل؟
                is_film = "/film/" in target_url
                print(f"🧐 النوع المتوقع: {'FILM 🎬' if is_film else 'SERIAL 📺'}", flush=True)

            except Exception as e:
                print(f"❌ خطأ في الاستخراج: {e}", flush=True)
                return {"error": str(e)}

            # 2. الدخول للصفحة
            print(f"🚀 الدخول للصفحة المستهدفة...", flush=True)
            page.goto(target_url, timeout=60000, wait_until="domcontentloaded")

            # 3. محاولة تحفيز المشغل (للأفلام)
            print("⏳ انتظار وتحريك الماوس لتحفيز المشغل...", flush=True)
            for i in range(10):
                page.mouse.move(100, 100 + (i*50))
                page.wait_for_timeout(1000)
            
            # طباعة عنوان الصفحة للتأكد
            print(f"📄 عنوان الصفحة الحالي: {page.title()}", flush=True)
            
            # 4. البحث عن Iframe (قد يكون المشغل داخل iframe)
            frames = page.frames
            print(f"🖼️ عدد الإطارات (Iframes) الموجودة: {len(frames)}", flush=True)
            for frame in frames:
                print(f"   - Frame URL: {frame.url}", flush=True)

        except Exception as e:
            print(f"💥 خطأ حرج: {e}", flush=True)
        finally:
            browser.close()

    return {"status": "Diagnostic complete, check Render logs"}

@app.route('/')
def index():
    return "Diagnostic Mode Active. Go to /debug?query=MovieName"

@app.route('/debug')
def debug():
    query = request.args.get('query')
    if not query: return "Missing query", 400
    return jsonify(run_diagnostic(query))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
