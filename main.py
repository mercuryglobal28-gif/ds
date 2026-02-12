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
# 2. تشغيل Node.js (Magic Proxy Solution)
# ==============================================================================
def run_node_script(config, hs_code):
    js_payload = f"""
    // --- 1. Global Setup ---
    const globalScope = typeof global !== 'undefined' ? global : this;

    // --- 2. THE MAGIC PROXY (The Black Hole) ---
    // هذا الكائن يوافق على كل شيء ولا يرفض أي طلب
    const MAGIC = new Proxy(function(){{}}, {{
        get: function(target, prop) {{
            // إذا طلب التحويل لنص أو رقم
            if (prop === Symbol.toPrimitive) return () => 0;
            if (prop === 'toString') return () => '0';
            if (prop === 'valueOf') return () => 0;
            
            // خصائص محددة لتجنب الأخطاء المنطقية
            if (prop === 'length') return 0;
            if (prop === 'style') return {{ display: 'block', visibility: 'visible' }};
            
            // دائماً أعد نفس الكائن السحري (Chainable)
            return MAGIC;
        }},
        set: function(target, prop, value) {{
            // وافق على أي عملية تعيين قيمة (حل مشكلة rating)
            return true;
        }},
        apply: function(target, thisArg, argumentsList) {{
            // إذا تم استدعاؤه كدالة، أعد نفسه
            return MAGIC;
        }},
        construct: function(target, args) {{
            return MAGIC;
        }}
    }});

    // --- 3. Mocking Browser Objects ---
    const window = {{
        location: {{ href: '{FULL_TARGET_URL}', hostname: 'kinovod120226.pro', origin: '{BASE_URL}', protocol: 'https:', pathname: '{TARGET_URI}', search: '' }},
        navigator: {{ userAgent: '{HEADERS['User-Agent']}', webdriver: false, plugins: [], languages: ['en-US'] }},
        screen: {{ width: 1920, height: 1080, colorDepth: 24 }},
        document: {{ cookie: '', referrer: '{BASE_URL}' }},
        history: {{ pushState: ()=>{{}}, replaceState: ()=>{{}} }},
        innerWidth: 1920,
        innerHeight: 1080,
        top: MAGIC,
        self: MAGIC,
        parent: MAGIC,
        localStorage: MAGIC,
        sessionStorage: MAGIC
    }};
    window.window = window;

    const document = {{
        location: window.location,
        cookie: '',
        referrer: '',
        getElementById: (id) => MAGIC,
        getElementsByTagName: (t) => [MAGIC],
        getElementsByClassName: (c) => [MAGIC],
        querySelector: (s) => MAGIC,
        querySelectorAll: (s) => [MAGIC],
        createElement: (t) => MAGIC,
        documentElement: MAGIC,
        body: MAGIC,
        head: MAGIC,
        addEventListener: (e, f) => {{ 
            // تشغيل الكود فوراً
            if(e==='DOMContentLoaded' || e==='load') setTimeout(f, 1); 
        }},
        attachEvent: (e, f) => setTimeout(f, 1)
    }};

    // --- 4. Expose Globals ---
    globalScope.window = window;
    globalScope.document = document;
    globalScope.location = window.location;
    globalScope.navigator = window.navigator;
    globalScope.screen = window.screen;
    globalScope.HTMLElement = function(){{}};

    // --- 5. Interception Logic ---
    function captureAndExit(data, url) {{
        const result = {{
            data: data,
            __url: url
        }};
        console.log("JSON_START" + JSON.stringify(result) + "JSON_END");
        process.exit(0);
    }}

    // Mock XMLHttpRequest
    class XMLHttpRequest {{
        open(method, url) {{ this.url = url; }}
        send(data) {{
            if (this.url && this.url.indexOf('user_data') !== -1) {{
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
        onreadystatechange() {{}}
    }}
    globalScope.XMLHttpRequest = XMLHttpRequest;

    // --- 6. JQUERY MOCK (Updated) ---
    // هنا الإصلاح الرئيسي: $ يعيد MAGIC، و $.fn هو MAGIC أيضاً
    const $ = function(param) {{
        if (typeof param === 'function') {{ setTimeout(param, 1); }}
        return MAGIC;
    }};
    
    // إضافة الخصائص المفقودة لـ jQuery
    $.fn = MAGIC;       // حل مشكلة $.fn.rating
    $.rating = MAGIC;   // حل احتياطي
    $.cookie = MAGIC;
    
    // اعتراض Ajax
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

    // --- 7. Inject Variables ---
    globalScope.MOVIE_ID = {config['MOVIE_ID']};
    globalScope.PLAYER_CUID = "{config['PLAYER_CUID']}";
    globalScope.IDENTIFIER = "{config['IDENTIFIER']}";

    // --- 8. Run Code ---
    // كسر الوقت لتنفيذ المؤقتات فوراً
    const originalSetTimeout = setTimeout;
    global.setTimeout = function(fn, delay) {{
        try {{ fn(); }} catch(e) {{}}
        return 1;
    }};

    try {{
        {hs_code}
    }} catch (e) {{
        console.error("RUNTIME_ERROR: " + e.message);
    }}
    
    // Safety timeout increased slightly
    originalSetTimeout(() => {{
        console.error("TIMEOUT: No ajax request intercepted within 3 seconds.");
    }}, 3000);
    """

    filename = "runner.js"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(js_payload)

    try:
        # تشغيل Node.js
        result = subprocess.run(["node", filename], capture_output=True, text=True, timeout=5)
        
        if os.path.exists(filename): os.remove(filename)

        output = result.stdout + result.stderr
        
        match = re.search(r'JSON_START(.*?)JSON_END', output)
        if match:
            return json.loads(match.group(1)), None
        else:
            return None, output

    except Exception as e:
        return None, f"Subprocess Error: {str(e)}"

# ==============================================================================
# 3. Endpoints
# ==============================================================================
@app.route('/')
def home():
    return "Magic Scraper Running."

@app.route('/get-json')
def fetch_data():
    config, result = fetch_assets()
    
    if result and len(result) > 500:
        hs_code = result
    else:
        return jsonify({"status": "error", "message": "Failed to download hs.js", "details": str(result)}), 500

    params, error_log = run_node_script(config, hs_code)
    
    if not params:
        return jsonify({
            "status": "error", 
            "message": "Signature generation failed", 
            "debug_log": error_log 
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
                "server_response_snippet": resp.text[:200]
            }), 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
