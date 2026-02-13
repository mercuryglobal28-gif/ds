from playwright.sync_api import sync_playwright
import json
import time

# ==============================================================================
# ⚙️ الإعدادات
# ==============================================================================
PROXY_SERVER = "46.161.47.123:9771"
PROXY_USER = "oFRHax"
PROXY_PASS = "4yFtU8"

TARGET_URL = "https://kinovod120226.pro/serial/259509-predatelstvo"

# ==============================================================================
# 🛡️ منطق الفلترة المتقدم (حظر شامل للوسائط والعناصر غير الضرورية)
# ==============================================================================
def intercept_network(route, request):
    url = request.url.lower()
    resource_type = request.resource_type

    # 🛑 1. حظر الملفات المحددة والأيقونات
    if any(x in url for x in ["master.js", "hls.js", "favicon", ".ico", ".svg"]):
        return route.abort()

    # 🛑 2. حظر الأنواع الثقيلة (الصور، الفيديو، الخطوط، التنسيقات)
    if resource_type in ["image", "media", "font", "stylesheet"]:
        return route.abort()
    
    # 🛑 3. حظر الامتدادات لضمان عدم تسرب أي وسائط
    extensions_to_block = [
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
        ".mp4", ".m3u8", ".ts", ".webm", ".avi", ".mkv"
    ]
    if any(url.endswith(ext) for ext in extensions_to_block):
        return route.abort()

    # ⚙️ 4. التعامل مع ملفات JavaScript الضرورية فقط
    if resource_type == "script":
        if "kinovod" in url or "hs.js" in url or "jquery" in url:
            return route.continue_()
        
        if any(x in url for x in ["google", "yandex", "facebook", "sentry", "ads"]):
            return route.abort()

        if "kinovod120226.pro" not in url:
            return route.abort()

    route.continue_()

# ==============================================================================
# 🚀 المشغل الرئيسي
# ==============================================================================
def run_hidden_spy():
    # 💡 headless=True تعني أن المتصفح سيختفي تماماً ويعمل في الخلفية
    print("🚀 تشغيل الجاسوس في الوضع المخفي تماماً (Headless & Incognito)...")
    
    captured_data = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,  # ✅ المتصفح مخفي تماماً
            proxy={
                "server": f"http://{PROXY_SERVER}",
                "username": PROXY_USER,
                "password": PROXY_PASS
            },
            args=[
                "--no-sandbox", 
                "--disable-gpu", 
                "--incognito", # ✅ وضع التصفح المتخفي
                "--blink-settings=imagesEnabled=false"
            ]
        )
        
        # إنشاء سياق جديد (Context) لضمان الخصوصية التامة
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
        page = context.new_page()

        # 1. تفعيل نظام الفلترة الشبكي
        page.route("**/*", intercept_network)

        # 2. حقن كود اعتراض البيانات وإخفاء الواجهة (لتقليل استهلاك المعالج)
        spy_script = """
        const style = document.createElement('style');
        style.textContent = `
            * { display: none !important; } /* حظر ظهور أي عنصر لتقليل جهد المعالجة */
        `;
        document.head.appendChild(style);

        const originalParse = JSON.parse;
        JSON.parse = function(text, reviver) {
            const result = originalParse(text, reviver);
            if (result && (Array.isArray(result) || result.items || text.includes('.mp4') || text.includes('.m3u8'))) {
                console.log('$$$CAPTURED$$$' + JSON.stringify(result));
            }
            return result;
        }
        """
        page.add_init_script(spy_script)

        # 3. الاستماع لرسائل الكونسول
        def handle_console(msg):
            nonlocal captured_data
            if "$$$CAPTURED$$$" in msg.text:
                print("🎯 تم التقاط البيانات المفكوكة بنجاح!")
                clean_json = msg.text.replace("$$$CAPTURED$$$", "")
                try:
                    captured_data = json.loads(clean_json)
                except:
                    pass

        page.on("console", handle_console)

        try:
            print(f"🌍 جاري العمل في الخلفية على الرابط: {TARGET_URL}")
            page.goto(TARGET_URL, timeout=90000, wait_until="commit")
            
            print("⏳ جاري انتظار فك التشفير التلقائي...")
            
            # حلقة انتظار ذكية
            for i in range(45): # زيادة الوقت قليلاً بسبب الوضع المخفي والبروكسي
                if captured_data:
                    break
                page.wait_for_timeout(1000)

        except Exception as e:
            print(f"⚠️ خطأ: {e}")
        
        finally:
            browser.close()

    # 4. معالجة وحفظ النتائج
    if captured_data:
        print("\n" + "="*50)
        print("🎉 البيانات النهائية المستخرجة:")
        print("="*50)
        print(json.dumps(captured_data, indent=4, ensure_ascii=False))
        
        filename = "final_hidden_result.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(captured_data, f, indent=4, ensure_ascii=False)
        print(f"\n📂 تم الحفظ في {filename}")
    else:
        print("❌ فشل التقاط البيانات. قد يكون السبب بطء البروكسي أو تغيير في الموقع.")

if __name__ == "__main__":
    run_hidden_spy()
