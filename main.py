import os
import json
from flask import Flask, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# ==============================================================================
# ⚙️ الإعدادات والمتغيرات العامة
# ==============================================================================
PROXY_SERVER = os.getenv("PROXY_SERVER", "46.161.47.123:9771")
PROXY_USER = os.getenv("PROXY_USER", "oFRHax")
PROXY_PASS = os.getenv("PROXY_PASS", "4yFtU8")
TARGET_URL = "https://kinovod120226.pro/serial/259509-predatelstvo"

# متغيرات للاحتفاظ بالمتصفح مفتوحاً
playwright_instance = None
browser_instance = None

# ==============================================================================
# 🛠️ دالة تشغيل المتصفح (تعمل مرة واحدة فقط)
# ==============================================================================
def get_browser():
    global playwright_instance, browser_instance
    
    # إذا كان المتصفح يعمل بالفعل، أعد استخدامه
    if browser_instance and browser_instance.is_connected():
        return browser_instance

    print("🔄 تشغيل المتصفح لأول مرة (أو إعادة تشغيله)...", flush=True)
    
    # إغلاق القديم إذا وجد لتنظيف الذاكرة
    if playwright_instance:
        try:
            playwright_instance.stop()
        except:
            pass

    playwright_instance = sync_playwright().start()
    
    browser_instance = playwright_instance.chromium.launch(
        headless=True,
        proxy={
            "server": f"http://{PROXY_SERVER}",
            "username": PROXY_USER,
            "password": PROXY_PASS
        },
        args=[
            "--no-sandbox", 
            "--disable-setuid-sandbox", 
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--blink-settings=imagesEnabled=false",
            "--mute-audio"
        ]
    )
    return browser_instance

# ==============================================================================
# 🛡️ منطق الفلترة (السريع)
# ==============================================================================
def intercept_network(route, request):
    # تحسينات السرعة القصوى (نفس المنطق السابق)
    resource_type = request.resource_type
    if resource_type in ["image", "media", "font", "stylesheet", "other"]:
        return route.abort()
    
    # السماح فقط للضروريات
    if resource_type in ["document", "xhr", "fetch", "script"]:
        return route.continue_()
        
    route.abort()

# ==============================================================================
# 🚀 دالة الجاسوس (تستخدم Context بدلاً من Browser جديد)
# ==============================================================================
def scrape_logic():
    global browser_instance
    print("🚀 بدء الاستخراج (باستخدام متصفح مفتوح)...", flush=True)
    captured_data = None
    context = None

    try:
        # الحصول على المتصفح المفتوح مسبقاً
        browser = get_browser()
        
        # ✅ إنشاء "سياق" جديد (Incognito) - هذا يضمن نظافة الكاش والكوكيز
        # في كل مرة يتم تشغيل هذه الدالة، نحصل على جلسة جديدة تماماً
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        
        # إعداد المهلة الزمنية للسياق
        context.set_default_timeout(30000)
        
        page = context.new_page()
        page.route("**/*", intercept_network)

        # حقن كود الجاسوس
        spy_script = """
        const originalParse = JSON.parse;
        JSON.parse = function(text, reviver) {
            try {
                const result = originalParse(text, reviver);
                if (result && (Array.isArray(result) || result.items)) {
                    console.log('$$$CAPTURED$$$' + JSON.stringify(result));
                }
                return result;
            } catch (e) { return originalParse(text, reviver); }
        }
        """
        page.add_init_script(spy_script)

        def handle_console(msg):
            nonlocal captured_data
            if "$$$CAPTURED$$$" in msg.text:
                clean_json = msg.text.replace("$$$CAPTURED$$$", "")
                try:
                    captured_data = json.loads(clean_json)
                except:
                    pass

        page.on("console", handle_console)

        print(f"🌍 طلب الصفحة...", flush=True)
        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=40000)
        except Exception as e:
            print(f"⚠️ تنبيه التحميل: {e}", flush=True)

        # حلقة انتظار سريعة
        for i in range(50):
            if captured_data:
                break
            page.wait_for_timeout(400) # فحص كل 0.4 ثانية

    except Exception as e:
        print(f"⚠️ خطأ حرج: {e}", flush=True)
        # إذا حدث خطأ في المتصفح نفسه، نقوم بتصفير المتغير ليعيد تشغيله المرة القادمة
        if "Target closed" in str(e) or "browser" in str(e).lower():
            browser_instance = None
        return {"error": str(e)}
    
    finally:
        # ✅ إغلاق السياق فقط! هذا يمسح الكاش والكوكيز لهذه الجلسة
        # لكنه يبقي المتصفح الرئيسي مفتوحاً للعميل التالي
        if context:
            context.close()

    return captured_data

# ==============================================================================
# 🌐 المسارات
# ==============================================================================
@app.route('/')
def index():
    return jsonify({
        "status": "Running",
        "mode": "Fast Context Switching ⚡"
    })

@app.route('/scrape')
def scrape():
    data = scrape_logic()
    if data:
        return jsonify(data)
    else:
        return jsonify({"status": "failed", "message": "No data captured"}), 500

if __name__ == "__main__":
    # تشغيل المتصفح عند بدء التطبيق (اختياري، لتسريع أول طلب)
    try:
        get_browser()
    except:
        pass
        
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
