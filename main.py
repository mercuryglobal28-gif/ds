from playwright.sync_api import sync_playwright
import json
import time
import re

# ==============================================================================
# ⚙️ الإعدادات
# ==============================================================================
PROXY_SERVER = "46.161.47.123:9771"
PROXY_USER = "oFRHax"
PROXY_PASS = "4yFtU8"

# جرب رابط فيلم هنا للتأكد
TARGET_URL = "https://kinovod120226.pro/film/259706-bokser" 

# ==============================================================================
# 🛡️ منطق الفلترة (معدل قليلاً للسماح بطلبات الفيديو)
# ==============================================================================
def intercept_network(route, request):
    url = request.url.lower()
    resource_type = request.resource_type

    # السماح بطلبات البيانات المهمة (JSON / XHR)
    if "vod" in url or "user_data" in url:
        return route.continue_()

    # حظر الموارد الثقيلة
    if resource_type in ["image", "media", "font", "stylesheet"]:
        return route.abort()
    
    if resource_type == "script":
        # السماح بالسكربتات الأساسية للموقع والمشغل
        if any(x in url for x in ["kinovod", "hs.js", "jquery", "player", "bundle", "hls"]):
            return route.continue_()
        
        # حظر التتبع والإعلانات
        if any(x in url for x in ["google", "yandex", "facebook", "sentry", "mc.yandex", "ads"]):
            return route.abort()

    route.continue_()

# ==============================================================================
# 🚀 المشغل الرئيسي (Universal Scraper)
# ==============================================================================
def run_universal_spy():
    print("🚀 تشغيل الجاسوس الشامل (أفلام + مسلسلات)...")
    
    # نستخدم حاوية لتخزين النتيجة للوصول إليها من داخل الدوال الفرعية
    result_container = {"data": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,  # وضع التخفي مفعل
            proxy={
                "server": f"http://{PROXY_SERVER}",
                "username": PROXY_USER,
                "password": PROXY_PASS
            },
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-gpu", 
                "--blink-settings=imagesEnabled=false"
            ]
        )
        
        page = browser.new_page()
        
        # 1. إعداد مراقب الشبكة (للأفلام)
        # ---------------------------------------------------------
        def handle_response(response):
            if result_container["data"]: return
            
            # الأفلام تطلب رابطاً يحتوي على /vod/
            if "/vod/" in response.url and response.status == 200:
                try:
                    data = response.json()
                    # التأكد أن الملف يحتوي على رابط فيديو
                    if isinstance(data, dict) and ("file" in data or "playlist" in data):
                        print(f"🎥 تم اصطياد JSON الفيلم من الشبكة: {response.url}")
                        result_container["data"] = data
                except: pass

        page.on("response", handle_response)
        page.route("**/*", intercept_network)

        # 2. حقن جاسوس JSON.parse (للمسلسلات)
        # ---------------------------------------------------------
        spy_script = """
        const originalParse = JSON.parse;
        JSON.parse = function(text, reviver) {
            try {
                const result = originalParse(text, reviver);
                // تصفية النتائج المفيدة فقط
                if (result && (Array.isArray(result) || result.file || result.items)) {
                    const str = JSON.stringify(result);
                    if (str.includes('.mp4') || str.includes('.m3u8')) {
                        console.log('$$$CAPTURED$$$' + str);
                    }
                }
                return result;
            } catch (e) { return originalParse(text, reviver); }
        }
        """
        page.add_init_script(spy_script)

        def handle_console(msg):
            if result_container["data"]: return
            if "$$$CAPTURED$$$" in msg.text:
                clean_json = msg.text.replace("$$$CAPTURED$$$", "")
                try:
                    print("📦 تم التقاط JSON المسلسل من الكونسول!")
                    result_container["data"] = json.loads(clean_json)
                except: pass

        page.on("console", handle_console)

        # 3. التنفيذ
        # ---------------------------------------------------------
        try:
            print(f"🌍 جاري التحميل: {TARGET_URL}")
            page.goto(TARGET_URL, timeout=60000, wait_until="domcontentloaded")
            
            # محاولة النقر على المشغل (مهم جداً للأفلام لتحفيز الطلب)
            try:
                print("👆 محاولة النقر على المشغل...")
                # محددات شائعة للمشغل
                page.click("#videoplayer", timeout=2000, force=True)
            except: pass

            print("⏳ انتظار البيانات...")
            for i in range(20): # 20 ثانية كحد أقصى
                if result_container["data"]:
                    break
                
                # 4. (احتياطي) فحص المتغيرات العامة في الصفحة
                if i > 5 and not result_container["data"]:
                    try:
                        manual_data = page.evaluate("() => window.flashvars || window.config || null")
                        if manual_data and manual_data.get('file'):
                            print("⚡ تم العثور على البيانات في متغيرات Window")
                            result_container["data"] = manual_data
                            break
                    except: pass

                page.wait_for_timeout(1000)
                # حركة بسيطة للماوس لمنع كشف البوت
                if i % 5 == 0: page.mouse.move(100, i*50)

        except Exception as e:
            print(f"⚠️ خطأ أثناء التشغيل: {e}")
        
        finally:
            browser.close()

    # معالجة النتائج النهائية
    captured_data = result_container["data"]
    if captured_data:
        print("\n" + "="*50)
        print("🎉 البيانات النهائية:")
        
        # تنظيف بسيط للروابط إذا كانت سلسلة نصية طويلة
        if "file" in captured_data and isinstance(captured_data["file"], str) and "[" in captured_data["file"]:
            print("💡 تم اكتشاف روابط متعددة، جاري التنسيق...")
            # (يمكنك إضافة كود تقسيم الروابط هنا إذا أردت)
            
        print(json.dumps(captured_data, indent=4, ensure_ascii=False))
    else:
        print("❌ لم يتم العثور على ملف JSON.")

if __name__ == "__main__":
    run_universal_spy()
