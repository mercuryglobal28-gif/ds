from playwright.sync_api import sync_playwright
import json
import time

# ==============================================================================
# ⚙️ الإعدادات الأساسية
# ==============================================================================
PROXY_SERVER = "46.161.47.123:9771"
PROXY_USER = "oFRHax"
PROXY_PASS = "4yFtU8"

TARGET_URL = "https://kinovod120226.pro/serial/259509-predatelstvo"

# ==============================================================================
# 🛡️ جدار الحماية الذكي (Network Filter)
# ==============================================================================
def intercept_network(route, request):
    url = request.url.lower()
    resource_type = request.resource_type

    # 1. حظر ملف master.js بناءً على طلبك
    if "master.js" in url:
        return route.abort()

    # 2. حظر الموارد البصرية الثقيلة (صور، خطوط، تنسيقات)
    if resource_type in ["image", "media", "font", "stylesheet"]:
        return route.abort()

    # 3. فلترة السكربتات (نسمح فقط بالمنطق الأساسي)
    if resource_type == "script":
        # السماح بملفات الموقع الأساسية (hs.js و jquery)
        if any(x in url for x in ["kinovod", "hs.js", "jquery"]):
            return route.continue_()
        
        # حظر الإعلانات والتحليلات
        if any(x in url for x in ["google", "yandex", "facebook", "ads"]):
            return route.abort()
        
        # حظر أي سكربت خارجي غير معروف
        if "kinovod120226.pro" not in url:
            return route.abort()

    return route.continue_()

# ==============================================================================
# 🚀 المشغل الرئيسي
# ==============================================================================
def run_ultimate_scraper():
    print("🚀 جاري تشغيل المستخرج النهائي (وضع النينجا المتقدم)...")
    
    captured_data = None

    with sync_playwright() as p:
        # إطلاق المتصفح
        browser = p.chromium.launch(
            headless=False, # اتركه False لمشاهدة اختفاء العناصر، أو True للسرعة القصوى
            proxy={
                "server": f"http://{PROXY_SERVER}",
                "username": PROXY_USER,
                "password": PROXY_PASS
            },
            args=["--no-sandbox", "--disable-gpu", "--blink-settings=imagesEnabled=false"]
        )
        
        page = browser.new_page()

        # 1. تفعيل فلتر الشبكة
        page.route("**/*", intercept_network)

        # 2. حقن "الجاسوس" و"قناع الإخفاء"
        # هذا السكربت ينفذ قبل أي شيء آخر في الصفحة
        spy_and_hide_script = """
        // --- أ. حظر وإخفاء النصوص، الأيقونات، والكلاس row ---
        const style = document.createElement('style');
        style.textContent = `
            * { 
                color: transparent !important; 
                fill: transparent !important; 
                text-shadow: none !important;
                background-image: none !important;
            }
            .row, .icon, [class*="icon-"], svg { 
                display: none !important; 
                visibility: hidden !important; 
            }
            html, body { background: #000 !important; }
        `;
        document.head.appendChild(style);

        // --- ب. حذف الكلاس row فيزيائياً من الـ DOM ---
        const observer = new MutationObserver(() => {
            document.querySelectorAll('.row').forEach(el => el.remove());
        });
        observer.observe(document.documentElement, { childList: true, subtree: true });

        // --- ج. اعتراض بيانات الفيديو (JSON.parse Hook) ---
        const originalParse = JSON.parse;
        JSON.parse = function(text, reviver) {
            const result = originalParse(text, reviver);
            // البحث عن كائن يحتوي على بيانات الفيديو (items أو روابط ملفات)
            if (result && (Array.isArray(result) || result.items || text.includes('.mp4'))) {
                console.log('$$$TARGET_DATA$$$' + JSON.stringify(result));
            }
            return result;
        };
        """
        page.add_init_script(spy_and_hide_script)

        # 3. الاستماع لرسائل الكونسول لالتقاط البيانات
        def handle_console(msg):
            nonlocal captured_data
            if "$$$TARGET_DATA$$$" in msg.text:
                print("🎯 تم التقاط بيانات الفيديو بنجاح!")
                try:
                    clean_json = msg.text.replace("$$$TARGET_DATA$$$", "")
                    captured_data = json.loads(clean_json)
                except Exception as e:
                    print(f"❌ خطأ في معالجة JSON: {e}")

        page.on("console", handle_console)

        try:
            print(f"🌍 جاري الاتصال بـ: {TARGET_URL}")
            # الانتقال للرابط (الانتظار حتى وصول الاستجابة الأولى)
            page.goto(TARGET_URL, timeout=60000, wait_until="commit")
            
            print("⏳ انتظار فك التشفير التلقائي...")
            
            # حلقة انتظار ذكية (30 ثانية كحد أقصى)
            for i in range(30):
                if captured_data:
                    break
                page.wait_for_timeout(1000)
                # تحفيز الصفحة بحركة بسيطة
                if i == 5: page.mouse.move(100, 100)

        except Exception as e:
            print(f"⚠️ حدث خطأ أثناء التصفح: {e}")
        
        finally:
            browser.close()

    # 4. طباعة وحفظ النتائج
    if captured_data:
        print("\n" + "="*50)
        print("🎉 البيانات المستخرجة:")
        print("="*50)
        print(json.dumps(captured_data, indent=4, ensure_ascii=False))
        
        with open("final_ninja_data.json", "w", encoding="utf-8") as f:
            json.dump(captured_data, f, indent=4, ensure_ascii=False)
        print(f"\n📂 تم حفظ النتيجة في: final_ninja_data.json")
    else:
        print("❌ لم يتم العثور على البيانات. تأكد من جودة البروكسي وصحة الرابط.")

if __name__ == "__main__":
    run_ultimate_scraper()
