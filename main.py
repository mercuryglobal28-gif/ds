from flask import Flask, jsonify
import execjs
import requests
import json
import re
import os

app = Flask(__name__)

# ==============================================================================
# إعدادات ثابتة
# ==============================================================================
BASE_URL = "https://kinovod120226.pro"
TARGET_URI = "/serial/259509-predatelstvo"
FULL_TARGET_URL = BASE_URL + TARGET_URI

# Headers لتقليل الحظر
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE_URL
}

# ==============================================================================
# 1. الدالة الذكية: جلب الصفحة واستخراج الملفات والمتغيرات
# ==============================================================================
def fetch_dynamic_assets():
    print("🚀 جاري جلب الصفحة الرئيسية لاستخراج البيانات...")
    try:
        response = requests.get(FULL_TARGET_URL, headers=HEADERS, timeout=10)
        html = response.text
        
        # 1. استخراج المتغيرات الأساسية من HTML
        # هذه المتغيرات تتغير، لذا سحبها من الصفحة أفضل من تثبيتها
        movie_id_match = re.search(r"MOVIE_ID\s*=\s*['\"]?(\d+)['\"]?", html)
        cuid_match = re.search(r"PLAYER_CUID\s*=\s*['\"]([^'\"]+)['\"]", html)
        ident_match = re.search(r"IDENTIFIER\s*=\s*['\"]([^'\"]+)['\"]", html)
        
        config = {
            "MOVIE_ID": movie_id_match.group(1) if movie_id_match else "259509",
            "PLAYER_CUID": cuid_match.group(1) if cuid_match else "unknown",
            "IDENTIFIER": ident_match.group(1) if ident_match else "unknown"
        }
        
        print(f"✅ تم استخراج الإعدادات: {config}")

        # 2. البحث عن رابط ملف hs.js
        # نبحث عن سطر مثل: <script src="/js/hs.js?v=123"></script>
        script_match = re.search(r'src="([^"]*hs\.js[^"]*)"', html)
        
        hs_code = ""
        if script_match:
            script_path = script_match.group(1)
            if not script_path.startswith("http"):
                script_url = BASE_URL + script_path
            else:
                script_url = script_path
                
            print(f"📥 جاري تحميل ملف الحماية من: {script_url}")
            js_response = requests.get(script_url, headers=HEADERS, timeout=10)
            hs_code = js_response.text
        else:
            raise Exception("لم يتم العثور على رابط ملف hs.js في الصفحة")

        return config, hs_code

    except Exception as e:
        print(f"❌ خطأ في الجلب الأوتوماتيكي: {e}")
        return None, None

# ==============================================================================
# 2. محرك JS
# ==============================================================================
def run_js_engine(config, hs_code):
    # بناء بيئة وهمية بناءً على البيانات المستخرجة
    js_env = f"""
    var window = {{
        location: {{
            href: '{FULL_TARGET_URL}',
            hostname: 'kinovod120226.pro',
            protocol: 'https:',
            origin: '{BASE_URL}'
        }},
        navigator: {{ userAgent: '{HEADERS['User-Agent']}' }},
        screen: {{ width: 1920, height: 1080 }},
        document: {{ cookie: '' }}
    }};
    var document = {{
        location: window.location,
        cookie: '',
        getElementById: function(id) {{ return null; }},
        getElementsByTagName: function(t) {{ return []; }},
        createElement: function(t) {{ return {{ style: {{}}, appendChild: function(){{}} }}; }},
        documentElement: {{ style: {{}} }}
    }};
    var location = window.location;
    var navigator = window.navigator;
    var screen = window.screen;
    var localStorage = {{ getItem: function(){{}}, setItem: function(){{}} }};
    
    // حقن المتغيرات التي سحبناها من الصفحة
    var MOVIE_ID = {config['MOVIE_ID']};
    var PLAYER_CUID = "{config['PLAYER_CUID']}";
    var IDENTIFIER = "{config['IDENTIFIER']}";

    var captured_params = {{}};
    
    // دالة Ajax الوهمية
    var $ = function(sel) {{ return {{ val: function(){{return 0}}, on: function(){{}}, text: function(){{}}, attr: function(){{}} }}; }};
    $.ajax = function(settings) {{
        if (settings.url && settings.url.indexOf('user_data') !== -1) {{
            captured_params = settings.data;
            captured_params['__url'] = settings.url;
        }}
        return {{ done: function(){{}}, fail: function(){{}} }};
    }};
    $.post = function() {{}};
    """

    full_script = js_env + "\n" + hs_code + "\n" + "function getData(){ return JSON.stringify(captured_params); }"
    
    try:
        # استخدام Node.js لتشغيل الكود
        ctx = execjs.get("Node").compile(full_script)
        data_str = ctx.call("getData")
        return json.loads(data_str)
    except Exception as e:
        print(f"❌ خطأ JS: {e}")
        return None

# ==============================================================================
# 3. نقاط النهاية (Endpoints)
# ==============================================================================
@app.route('/')
def home():
    return "Auto-Scraper is Ready. Go to /get-json"

@app.route('/get-json')
def fetch_data():
    # 1. الجلب الأوتوماتيكي للملفات
    config, hs_code = fetch_dynamic_assets()
    
    if not hs_code:
        return jsonify({"status": "error", "message": "Failed to fetch hs.js dynamically"}), 500

    # 2. توليد التوقيع
    params = run_js_engine(config, hs_code)
    
    if not params:
        return jsonify({"status": "error", "message": "Failed to generate signature"}), 500

    # 3. إرسال الطلب للسيرفر
    api_url = BASE_URL + params.pop('__url', '/user_data')
    
    # تحديث الهيدرز لتبدو كطلب Ajax حقيقي
    req_headers = HEADERS.copy()
    req_headers.update({
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE_URL
    })
    
    try:
        resp = requests.get(api_url, params=params, headers=req_headers, timeout=10)
        
        # البحث عن JSON داخل الرد
        match = re.search(r'(\[.*\])', resp.text, re.DOTALL)
        if match:
            clean_data = json.loads(match.group(1))
            return jsonify({
                "status": "success", 
                "config_used": config, # للتأكد من البيانات المستخدمة
                "data": clean_data
            })
        else:
            return jsonify({
                "status": "error", 
                "message": "Invalid response format", 
                "raw_response_snippet": resp.text[:200]
            }), 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    # تشغيل التطبيق
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
