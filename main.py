from flask import Flask, jsonify
import subprocess
import requests
import json
import re
import os
import time

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
    "Origin": BASE_URL,
    "Accept-Language": "en-US,en;q=0.9"
}

# ==============================================================================
# 1. جلب الملفات
# ==============================================================================
def fetch_assets():
    try:
        response = requests.get(FULL_TARGET_URL, headers=HEADERS, timeout=15)
        html = response.text
        
        config = {
            "MOVIE_ID": "259509",
            "PLAYER_CUID": "unknown",
            "IDENTIFIER": "unknown"
        }
        
        # Regex مرن لاستخراج البيانات
        m_id = re.search(r"MOVIE_ID\s*[:=]\s*['\"]?(\d+)['\"]?", html)
        if m_id: config["MOVIE_ID"] = m_id.group(1)
            
        cuid = re.search(r"PLAYER_CUID\s*[:=]\s*['\"]([^'\"]+)['\"]", html)
        if cuid: config["PLAYER_CUID"] = cuid.group(1)
            
        ident = re.search(r"IDENTIFIER\s*[:=]\s*['\"]([^'\"]+)['\"]", html)
        if ident: config["IDENTIFIER"] = ident.group(1)
        
        # البحث عن hs.js
        script_match = re.search(r'src="([^"]*hs\.js[^"]*)"', html)
        if script_match:
            script_url = script_match.group(1)
            if not script_url.startswith("http"): script_url = BASE_URL + script_url
            
            js_resp = requests.get(script_url, headers=HEADERS, timeout=15)
            return config, js_resp.text
        else:
            return config, None

    except Exception as e:
        return None, str(e)

# ==============================================================================
# 2. تشغيل Node.js (بيئة التصحيح القصوى)
# ==============================================================================
def run_node_script(config, hs_code):
    js_payload = f"""
    // --- 1. Global Setup ---
    const globalScope = typeof global !== 'undefined' ? global : this;
    
    // --- 2. Mocking Browser Objects ---
    const window = {{
        location: {{ href: '{FULL_TARGET_URL}', hostname: 'kinovod120226.pro', origin: '{BASE_URL}', protocol: 'https:', pathname: '{TARGET_URI}', search: '' }},
        navigator: {{ userAgent: '{HEADERS['User-Agent']}', webdriver: false, plugins: [], languages: ['en-US'] }},
        screen: {{ width: 1920, height: 1080, colorDepth: 24 }},
        document: {{ cookie: '', referrer: '{BASE_URL}' }},
        history: {{ pushState: ()=>{{}}, replaceState: ()=>{{}} }},
        innerWidth: 1920,
        innerHeight: 1080,
        top: null,
        self: null,
        localStorage: {{ getItem: ()=>null, setItem: ()=>{{}} }},
        sessionStorage: {{ getItem: ()=>null, setItem: ()=>{{}} }}
    }};
    window.top = window;
    window.self = window;
    window.window = window;

    // Document Proxy to handle getElementById etc.
    const elementProxy = new Proxy({{}}, {{
        get: (target, prop) => {{
            if(prop === 'style') return {{ display: 'block' }};
            if(prop === 'value') return '0';
            if(prop === 'innerHTML') return '';
            if(prop === 'getAttribute') return ()=>null;
            if(prop === 'appendChild') return ()=>elementProxy;
            return elementProxy; // Chainable
        }}
    }});
    
    const document = {{
        location: window.location,
        cookie: '',
        referrer: '',
        getElementById: (id) => elementProxy,
        getElementsByTagName: (t) => [elementProxy],
        querySelector: (s) => elementProxy,
        querySelectorAll: (s) => [elementProxy],
        createElement: (t) => elementProxy,
        documentElement: {{ style: {{}} }},
        body: elementProxy,
        head: elementProxy,
        addEventListener: (e, f) => {{ 
            if(e==='DOMContentLoaded') setTimeout(f, 10); 
        }}
    }};

    // --- 3. Expose Globals ---
    globalScope.window = window;
    globalScope.document = document;
    globalScope.location = window.location;
    globalScope.navigator = window.navigator;
    globalScope.screen = window.screen;

    // --- 4. Interception Logic (The Trap) ---
    function captureAndExit(data, url) {{
        const result = {{
            data: data,
            __url: url
        }};
        console.log("JSON_START" + JSON.stringify(result) + "JSON_END");
        process.exit(0);
    }}

    // Mock XMLHttpRequest (Fallback)
    class XMLHttpRequest {{
        open(method, url) {{ this.url = url; }}
        send(data) {{
            if (this.url && this.url.indexOf('user_data') !== -1) {{
                // Parse query string if data is null
                let params = {{}};
                if (this.url.includes('?')) {{
                     const searchParams = new URLSearchParams(this.url.split('?')[1]);
                     for(const [key, value] of searchParams) params[key] = value;
                }}
                captureAndExit(params, this.url.split('?')[0]);
            }}
        }}
        setRequestHeader() {{}}
        withCredentials = false;
    }}
    globalScope.XMLHttpRequest = XMLHttpRequest;

    // Mock jQuery (Primary)
    const $ = function(param) {{
        if (typeof param === 'function') {{ setTimeout(param, 1); }}
        return {{
            val: () => '0',
            on: () => {{}},
            text: () => {{}},
            attr: () => {{}},
            css: () => {{}},
            ready: (fn) => {{ if(fn) setTimeout(fn, 1); }},
            click: () => {{}}
        }};
    }};
    
    $.ajax = function(settings) {{
        if (settings.url && settings.url.indexOf('user_data') !== -1) {{
            captureAndExit(settings.data, settings.url);
        }}
        return {{ done: ()=>{{}}, fail: ()=>{{}} }};
    }};
    $.post = function() {{}};
    
    globalScope.$ = $;
    globalScope.jQuery = $;
    window.$ = $;
    window.jQuery = $;

    // --- 5. Inject Variables ---
    globalScope.MOVIE_ID = {config['MOVIE_ID']};
    globalScope.PLAYER_CUID = "{config['PLAYER_CUID']}";
    globalScope.IDENTIFIER = "{config['IDENTIFIER']}";

    // --- 6. Run the Code safely ---
    try {{
        {hs_code}
    }} catch (e) {{
        console.error("RUNTIME_ERROR: " + e.message);
    }}
    
    // Safety timeout: if nothing happens in 2 seconds
    setTimeout(() => {{
        console.error("TIMEOUT: No ajax request intercepted within 2 seconds.");
    }}, 2000);
    """

    filename = "runner.js"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(js_payload)

    try:
        # تشغيل Node.js
        result = subprocess.run(["node", filename], capture_output=True, text=True, timeout=5)
        
        if os.path.exists(filename): os.remove(filename)

        output = result.stdout + result.stderr # ندمج المخرجات لرؤية الأخطاء
        
        match = re.search(r'JSON_START(.*?)JSON_END', output)
        if match:
            return json.loads(match.group(1)), None
        else:
            return None, output # إرجاع نص الخطأ كاملاً للتشخيص

    except Exception as e:
        return None, f"Subprocess Error: {str(e)}"

# ==============================================================================
# 3. Endpoints
# ==============================================================================
@app.route('/')
def home():
    return "Debugger Scraper Running."

@app.route('/get-json')
def fetch_data():
    config, result = fetch_assets()
    
    # إذا كان result هو كود JS (نص طويل)
    if result and len(result) > 500:
        hs_code = result
    else:
        return jsonify({"status": "error", "message": "Failed to download hs.js", "details": str(result)}), 500

    # تشغيل Node
    params, error_log = run_node_script(config, hs_code)
    
    if not params:
        # هنا سنعرف السبب الحقيقي للفشل!
        return jsonify({
            "status": "error", 
            "message": "Signature generation failed", 
            "debug_log": error_log # <--- هذا السطر سيخبرنا بالمشكلة
        }), 500

    # تجهيز الطلب
    api_path = params.pop('__url', '/user_data')
    if api_path.startswith("http"): api_url = api_path
    else: api_url = BASE_URL + api_path
    
    req_headers = HEADERS.copy()
    req_headers.update({
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE_URL,
    })
    
    try:
        # إرسال الطلب مع التوقيع
        resp = requests.get(api_url, params=params, headers=req_headers, timeout=10)
        
        # استخراج JSON
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
                "server_response_snippet": resp.text[:200]
            }), 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
