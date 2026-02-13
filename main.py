# ==============================================================================
# 🔍🚀 المنطق الرئيسي: بحث + استخراج (مصحح للأفلام والمسلسلات)
# ==============================================================================
def search_and_scrape(query_text):
    global browser_instance
    print(f"🔎 البحث عن: {query_text}", flush=True)
    
    captured_data = None
    context = None
    page = None

    try:
        browser = get_browser()
        # نستخدم ignore_https_errors لتجنب توقف المتصفح بسبب شهادات الأمان
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            ignore_https_errors=True 
        )
        context.set_default_timeout(60000)
        page = context.new_page()
        page.route("**/*", intercept_network)

        # ---------------------------------------------------------
        # 1️⃣ المرحلة الأولى: البحث
        # ---------------------------------------------------------
        search_url = f"{BASE_URL}/search?query={query_text}"
        try:
            page.goto(search_url, wait_until="domcontentloaded")
        except:
            pass 

        # البحث عن رابط مسلسل أو فيلم
        try:
            page.wait_for_selector("a[href*='/serial/'], a[href*='/film/']", timeout=10000)
            element = page.query_selector("a[href*='/serial/'], a[href*='/film/']")
            
            if not element:
                print("❌ لم يتم العثور على نتائج.", flush=True)
                return {"error": "Not found"}
            
            found_href = element.get_attribute("href")
            full_target_url = BASE_URL + found_href
            print(f"✅ تم العثور على الرابط: {full_target_url}", flush=True)

        except Exception as e:
            print(f"❌ خطأ في البحث: {e}", flush=True)
            return {"error": "Search failed"}

        # ---------------------------------------------------------
        # 2️⃣ المرحلة الثانية: الاستخراج (Spy المعدل)
        # ---------------------------------------------------------
        
        # 👇 التعديل الجوهري هنا 👇
        spy_script = """
        const originalParse = JSON.parse;
        JSON.parse = function(text, reviver) {
            try {
                const result = originalParse(text, reviver);
                
                // التعديل: نقبل المصفوفات (المسلسلات) أو الكائنات التي تحتوي على رابط ملف (الأفلام)
                if (result) {
                    if (Array.isArray(result) || result.items || result.file || result.hls) {
                        console.log('$$$CAPTURED$$$' + JSON.stringify(result));
                    }
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
                    data = json.loads(clean_json)
                    # تصفية إضافية: التأكد أن البيانات مفيدة
                    if isinstance(data, list) or (isinstance(data, dict) and ("file" in data or "id" in data)):
                        captured_data = data
                except:
                    pass

        page.on("console", handle_console)

        print(f"🚀 الانتقال للصفحة...", flush=True)
        try:
            page.goto(full_target_url, wait_until="domcontentloaded", timeout=45000)
        except:
            pass

        # انتظار البيانات (مع تحريك الماوس قليلاً للأفلام لأنها أحياناً تتطلب تفاعلاً)
        for i in range(60): # 30 ثانية كحد أقصى
            if captured_data:
                break
            page.wait_for_timeout(500)
            
            # حركة بسيطة للماوس قد تحفز تحميل مشغل الفيديو في الأفلام
            if i % 5 == 0:
                try: page.mouse.move(100, 100 + i)
                except: pass

    except Exception as e:
        print(f"⚠️ خطأ: {e}", flush=True)
        # إعادة تعيين المتصفح عند الأخطاء الكبيرة فقط
        if "Target closed" in str(e):
            browser_instance = None
        return {"error": str(e)}
    
    finally:
        if context:
            context.close()

    return captured_data
