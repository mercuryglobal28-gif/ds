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
    "Referer": BASE_URL,
    "Origin": BASE_URL
}

# ==============================================================================
# 1. جلب الملفات والمتغيرات (Scraping)
# ==============================================================================
def fetch_assets():
    print("🚀 جلب الصفحة لاستخراج البيانات...")
    try:
        response = requests.get(FULL_TARGET_URL, headers=HEADERS, timeout=15)
        html = response.text
        
        # استخراج المتغيرات (مع قيم افتراضية للحماية)
        config = {
            "MOVIE_ID": "259509",
            "PLAYER_CUID": "unknown",
            "IDENTIFIER": "unknown"
        }
        
        m_id = re.search(r"MOVIE_ID\s*=\s*['\"]?(\d+)['\"]?", html)
        if m_id: config["MOVIE_ID"] = m_id.group(1)
            
        cuid = re.search(r"PLAYER_CUID\s*=\s*['\"]([^'\"]+)['\"]", html)
        if cuid: config["PLAYER_CUID"] = cuid.group(1)
            
        ident = re.search(r"IDENTIFIER\s*=\s*['\"]([^'\"]+)['\"]", html)
        if ident: config["IDENTIFIER"] = ident.group(1)
        
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
# 2. تشغيل Node.js مع بيئة وهمية متطورة (Robust Environment)
# ==============================================================================
def run_node_script(config, hs_code):
    js_payload = f"""
    // ============================================================
    // 1. نظام "الجوكر" (Universal Proxy)
    // هذا يمنع السكربت من الانهيار إذا طلب أي عنصر غير موجود
    // ============================================================
    const safeObj = new Proxy({{}}, {{
        get: function(target, prop) {{
            if (prop === 'style') return {{}}; // دائماً يعيد ستايل فارغ
            if (prop === 'value') return '0';
            if (prop === 'innerHTML') return '';
            if (prop === 'length') return 0;
            // إذا تم استدعاؤه كدالة، أعد نفس الكائن
            return () => safeObj; 
        }}
    }});

    // ============================================================
    // 2. محاكاة المتصفح (Browser Mock)
    // ============================================================
    const window = {{
        location: {{ href: '{FULL_TARGET_URL}', hostname: 'kinovod120226.pro', origin: '{BASE_URL}', protocol: 'https:' }},
        navigator: {{ userAgent: '{HEADERS['User-Agent']}', webdriver: false, plugins: [] }},
        screen: {{ width: 1920, height: 1080 }},
        document: {{ cookie: '' }},
        top: {{ location: {{ href: '{FULL_TARGET_URL}' }} }},
        self: {{}},
        localStorage: {{ getItem: ()=>null, setItem: ()=>{{}} }},
        sessionStorage: {{ getItem: ()=>null, setItem: ()=>{{}} }}
    }};
    window.self = window; // Circular reference

    const document = {{
        location: window.location,
        cookie: '',
        referrer: '',
        // استخدام الجوكر لأي بحث عن العناصر
        getElementById: (id) => safeObj,
        getElementsByTagName: (t) => [safeObj],
        querySelector: (s) => safeObj,
        querySelectorAll: (s) => [safeObj],
        createElement: (t) => safeObj,
        documentElement: {{ style: {{}} }},
        body: safeObj
    }};

    const location = window.location;
    const navigator = window.navigator;
    const screen = window.screen;

    // ============================================================
    // 3. كسر الوقت (Time Travel)
    // نجبر أي مؤقت على العمل فوراً بدلاً من الانتظار
    // ============================================================
    const originalSetTimeout = setTimeout;
    global.setTimeout = function(fn, delay) {{
        try {{ fn(); }} catch(e) {{}} // نفذ فوراً!
        return 1;
    }};
    global.setInterval = function(fn, delay) {{
        try {{ fn(); }} catch(e) {{}} // نفذ مرة واحدة فوراً
        return 1;
    }};

    // ============================================================
    // 4. المتغيرات والاعتراض (Injection)
    // ============================================================
    const MOVIE_ID = {config['MOVIE_ID']};
    const PLAYER_CUID = "{config['PLAYER_CUID']}";
    const IDENTIFIER = "{config['IDENTIFIER']}";

    // محاكاة jQuery
    const $ = function(param) {{
        if (typeof param === 'function') param(); // تشغيل $(document).ready
        return {{
            val: () => '0',
            on: () => {{}},
            text: () => {{}},
            attr: () => {{}},
            css: () => {{}},
            ready: (fn) => {{ if(fn) fn(); }},
            click: () => {{}}
        }};
    }};
    
    $.ajax = function(settings) {{
        if (settings.url && settings.url.indexOf('user_data') !== -1) {{
            settings.data['__url'] = settings.url;
            console.log("JSON_START" + JSON.stringify(settings.data) + "JSON_END");
            process.exit(0); // إنهاء ناجح فوراً
        }}
        return {{ done: ()=>{{}}, fail: ()=>{{}} }};
    }};
    $.post = function() {{}};

    // ============================================================
    // 5. تشغيل الكود المشفر
    // ============================================================
    try {{
        {hs_code}
    }} catch (e) {{
        // تجاهل الأخطاء، المهم أن $.ajax تم استدعاؤه قبل الخطأ
    }}
    """

    filename = "runner.js"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(js_payload)

    try:
        # تشغيل Node.js
        result = subprocess.run(["node", filename], capture_output=True, text=True, timeout=5)
        
        if os.path.exists(filename): os.remove(filename)

        # استخراج JSON بدقة (بين العلامات)
        output = result.stdout
        match = re.search(r'JSON_START(.*?)JSON_END', output)
        if match:
            return json.loads(match.group(1))
        else:
            print(f"⚠️ Node Error Output: {result.stderr}")
            print(f"⚠️ Node Stdout: {output}")
            return None

    except Exception as e:
        print(f"❌ خطأ subprocess: {e}")
        return None

# ==============================================================================
# 3. Endpoints
# ==============================================================================
@app.route('/')
def home():
    return "Robust Scraper Running."

@app.route('/get-json')
def fetch_data():
    config, hs_code = fetch_assets()
    if not hs_code:
        return jsonify({"status": "error", "message": "Failed to download hs.js"}), 500

    params = run_node_script(config, hs_code)
    
    if not params:
        return jsonify({"status": "error", "message": "Signature generation failed"}), 500

    api_path = params.pop('__url', '/user_data')
    api_url = BASE_URL + api_path
    
    # تحديث الهيدرز لتطابق المتصفح
    req_headers = HEADERS.copy()
    req_headers.update({
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE_URL,
        "Accept": "application/json, text/javascript, */*; q=0.01"
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
            return jsonify({
                "status": "error", 
                "message": "Invalid response from server", 
                "server_response": resp.text[:500]
            }), 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
