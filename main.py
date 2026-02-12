from flask import Flask, jsonify
import subprocess
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE_URL
}

# ==============================================================================
# 1. جلب الملفات والمتغيرات (Scraping)
# ==============================================================================
def fetch_assets():
    print("🚀 جلب الصفحة لاستخراج البيانات...")
    try:
        response = requests.get(FULL_TARGET_URL, headers=HEADERS, timeout=15)
        html = response.text
        
        # استخراج المتغيرات
        movie_id = re.search(r"MOVIE_ID\s*=\s*['\"]?(\d+)['\"]?", html)
        cuid = re.search(r"PLAYER_CUID\s*=\s*['\"]([^'\"]+)['\"]", html)
        ident = re.search(r"IDENTIFIER\s*=\s*['\"]([^'\"]+)['\"]", html)
        
        config = {
            "MOVIE_ID": movie_id.group(1) if movie_id else "259509",
            "PLAYER_CUID": cuid.group(1) if cuid else "unknown",
            "IDENTIFIER": ident.group(1) if ident else "unknown"
        }
        
        # استخراج رابط hs.js
        script_match = re.search(r'src="([^"]*hs\.js[^"]*)"', html)
        if script_match:
            script_url = script_match.group(1)
            if not script_url.startswith("http"): script_url = BASE_URL + script_url
            
            print(f"📥 تحميل hs.js من: {script_url}")
            js_resp = requests.get(script_url, headers=HEADERS, timeout=15)
            return config, js_resp.text
        else:
            return config, None

    except Exception as e:
        print(f"❌ خطأ في الجلب: {e}")
        return None, None

# ==============================================================================
# 2. تشغيل Node.js مباشرة (تجاوز مشاكل المكتبات)
# ==============================================================================
def run_node_script(config, hs_code):
    # بناء بيئة وهمية قوية جداً
    # السر هنا في دالة $: إذا تم تمرير دالة لها، ننفذها فوراً!
    js_payload = f"""
    // 1. بيئة وهمية (Mock Environment)
    const window = {{
        location: {{ href: '{FULL_TARGET_URL}', hostname: 'kinovod120226.pro', origin: '{BASE_URL}', protocol: 'https:' }},
        navigator: {{ userAgent: '{HEADERS['User-Agent']}' }},
        screen: {{ width: 1920, height: 1080 }},
        document: {{ cookie: '' }}
    }};
    const document = {{
        location: window.location,
        cookie: '',
        // كائن سحري يمنع الأخطاء عند البحث عن العناصر
        getElementById: function(id) {{ return {{ value: '0', innerHTML: '', style: {{}} }}; }},
        getElementsByTagName: function(t) {{ return []; }},
        createElement: function(t) {{ return {{ style: {{}}, appendChild: function(){{}} }}; }},
        documentElement: {{ style: {{}} }}
    }};
    const location = window.location;
    const navigator = window.navigator;
    const screen = window.screen;
    const localStorage = {{ getItem: ()=>null, setItem: ()=>{{}} }};

    // المتغيرات المستخرجة
    const MOVIE_ID = {config['MOVIE_ID']};
    const PLAYER_CUID = "{config['PLAYER_CUID']}";
    const IDENTIFIER = "{config['IDENTIFIER']}";

    // مخزن النتيجة
    let captured_params = null;

    // 2. محاكاة jQuery الذكية (هذا هو سبب الحل)
    const $ = function(param) {{
        // إذا كان المدخل دالة (مثل $(document).ready)، نفذها فوراً!
        if (typeof param === 'function') {{
            param();
        }}
        return {{
            val: function() {{ return '0'; }},
            on: function() {{}},
            text: function() {{}},
            attr: function() {{}},
            css: function() {{}},
            ready: function(fn) {{ if(fn) fn(); }} // تنفيذ ready فوراً
        }};
    }};
    
    // اعتراض Ajax
    $.ajax = function(settings) {{
        if (settings.url && settings.url.indexOf('user_data') !== -1) {{
            captured_params = settings.data;
            captured_params['__url'] = settings.url;
            
            // طباعة النتيجة فوراً للخروج
            console.log(JSON.stringify(captured_params));
        }}
        return {{ done: ()=>{{}}, fail: ()=>{{}} }};
    }};
    $.post = function() {{}};

    // 3. كود الموقع الأصلي
    try {{
        {hs_code}
    }} catch (e) {{
        // نتجاهل أخطاء hs.js غير المؤثرة
    }}
    """

    # كتابة الكود في ملف مؤقت
    filename = "runner.js"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(js_payload)

    try:
        # تشغيل Node.js
        result = subprocess.run(["node", filename], capture_output=True, text=True, timeout=5)
        
        # تنظيف الملف
        if os.path.exists(filename): os.remove(filename)

        # قراءة الناتج (JSON)
        output = result.stdout.strip()
        if output and "{" in output:
            # أحياناً يطبع Node تحذيرات، نأخذ آخر سطر json
            json_str = output.split('\n')[-1]
            return json.loads(json_str)
        else:
            print(f"⚠️ Node Output Error: {result.stderr}")
            return None

    except Exception as e:
        print(f"❌ خطأ subprocess: {e}")
        return None

# ==============================================================================
# 3. API Endpoints
# ==============================================================================
@app.route('/')
def home():
    return "Node-Powered Scraper is Running."

@app.route('/get-json')
def fetch_data():
    # 1. جلب الكود الأصلي
    config, hs_code = fetch_assets()
    if not hs_code:
        return jsonify({"status": "error", "message": "Failed to download hs.js"}), 500

    # 2. تشغيل التشفير
    params = run_node_script(config, hs_code)
    
    if not params:
        return jsonify({"status": "error", "message": "Failed to generate signature (Mock Environment Issue)"}), 500

    # 3. إرسال الطلب النهائي
    api_path = params.pop('__url', '/user_data')
    api_url = BASE_URL + api_path
    
    req_headers = HEADERS.copy()
    req_headers.update({
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE_URL
    })
    
    try:
        resp = requests.get(api_url, params=params, headers=req_headers, timeout=10)
        
        match = re.search(r'(\[.*\])', resp.text, re.DOTALL)
        if match:
            return jsonify({
                "status": "success", 
                "data": json.loads(match.group(1))
            })
        else:
            # في حال فشل، نعرض الرد لنعرف السبب
            return jsonify({
                "status": "error", 
                "message": "Invalid response from server", 
                "server_response": resp.text[:500]
            }), 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
