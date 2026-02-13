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
# 🔒 إعدادات البروكسي
# ==============================================================================
PROXY_HOST = "46.161.47.123:9771"
PROXY_USER = "oFRHax"
PROXY_PASS = "4yFtU8"
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}"
PROXIES = { "http": PROXY_URL, "https": PROXY_URL }

# ==============================================================================
# 1. جلب الملفات
# ==============================================================================
def fetch_assets():
    try:
        response = requests.get(FULL_TARGET_URL, headers=HEADERS, proxies=PROXIES, timeout=20)
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
        
        script_match = re.search(r'src="([^"]*hs\.js[^"]*)"', html)
        if script_match:
            script_url = script_match.group(1)
            if not script_url.startswith("http"): script_url = BASE_URL + script_url
            
            js_resp = requests.get(script_url, headers=HEADERS, proxies=PROXIES, timeout=20)
            return config, js_resp.text
        else:
            return config, None
    except Exception as e:
        return None, str(e)

# ==============================================================================
# 2. تشغيل Node.js (Smart jQuery Mock)
# ==============================================================================
def run_node_script(config, hs_code):
    js_payload = f"""
    // --- 1. Global Setup ---
    const globalScope = typeof global !== 'undefined' ? global : this;

    // --- 2. JQUERY MOCK (The Fix) ---
    // هذا الكائن يحاكي دوال jQuery الحقيقية
    const JQ_METHODS = {{
        // الوظيفة الأهم: المحاكاة للتكرار
        each: function(callback) {{
            // نتظاهر بأننا وجدنا عنصراً واحداً وننفذ الكود عليه
            if (typeof callback === 'function') {{
                try {{
                    // call(context, index, element)
                    callback.call(this, 0, this); 
                }} catch(e) {{}}
            }}
            return this;
        }},
        // التعامل مع البيانات
        data: function(k, v) {{
            if (v === undefined) return {{}}; 
            return this;
        }},
        // دوال التنسيق والـ DOM (Chainable)
        css: function() {{ return this; }},
        attr: function() {{ return ''; }},
        prop: function() {{ return false; }},
        val: function() {{ return '0'; }},
        width: function() {{ return 100; }},
        height: function() {{ return 100; }},
        offset: function() {{ return {{left:0, top:0}}; }},
        index: function() {{ return 0; }},
        
        // التلاعب بالعناصر
        append: function() {{ return this; }},
        appendTo: function() {{ return this; }},
        insertBefore: function() {{ return this; }},
        find: function() {{ return this; }},
        slice: function() {{ return this; }},
        eq: function() {{ return this; }},
        
        // الأحداث
        on: function() {{ return this; }},
        trigger: function() {{ return this; }},
        unbind: function() {{ return this; }}
    }};

    // Proxy للتعامل مع أي دالة غير معرفة (Chainable)
    const JQ_PROXY_HANDLER = {{
        get: function(target, prop) {{
            if (prop in target) return target[prop];
            // إذا طلب دالة غير موجودة، أعد دالة ترجع الـ Proxy نفسه
            return function() {{ return new Proxy(target, JQ_PROXY_HANDLER); }};
        }},
        set: function() {{ return true; }}
    }};

    // الدالة الرئيسية $
    const $ = function(selector) {{
        // إذا كان المدخل دالة (document.ready)، نفذها فوراً
        if (typeof selector === 'function') {{
            setTimeout(selector, 10);
            return;
        }}
        // أعد كائن jQuery الوهمي
        return new Proxy(JQ_METHODS, JQ_PROXY_HANDLER);
    }};

    // ربط الـ Prototype (مهم جداً للإضافات مثل rating)
    $.fn = JQ_METHODS;
    
    // أدوات jQuery المساعدة
    $.extend = function(target, ...sources) {{ return target || {{}}; }};
    $.noop = function() {{}};
    $.isFunction = function(f) {{ return typeof f === 'function'; }};
    
    // اعتراض Ajax
    $.ajax = function(settings) {{
        if (settings.url && settings.url.indexOf('user_data') !== -1) {{
            captureAndExit(settings.data, settings.url);
        }}
        return {{ done: ()=>{{}}, fail: ()=>{{}} }};
    }};
    $.post = function() {{}};

    // نشر jQuery للعامة
    globalScope.$ = $;
    globalScope.jQuery = $;
    
    // --- 3. DOM Mock ---
    const domProxy = new Proxy({{}}, {{
        get: (t, p) => {{
            if (p==='style') return {{}};
            if (p==='value') return '0';
            return domProxy;
        }},
        set: ()=>true
    }});
    
    const window = {{
        location: {{ href: '{FULL_TARGET_URL}', hostname: 'kinovod120226.pro', origin: '{BASE_URL}', protocol: 'https:', pathname: '{TARGET_URI}', search: '' }},
        navigator: {{ userAgent: '{HEADERS['User-Agent']}' }},
        document: {{ cookie: '' }},
        screen: {{ width: 1920, height: 1080 }},
        top: domProxy, self: domProxy,
        localStorage: {{ getItem: ()=>null, setItem: ()=>{{}} }},
        sessionStorage: {{ getItem: ()=>null, setItem: ()=>{{}} }},
        console: console
    }};
    window.window = window;

    const document = {{
        location: window.location,
        cookie: '',
        referrer: '{BASE_URL}',
        getElementById: () => domProxy,
        getElementsByTagName: () => [domProxy],
        querySelector: () => domProxy,
        querySelectorAll: () => [domProxy],
        createElement: () => domProxy,
        documentElement: {{ style: {{}} }},
        body: domProxy,
        addEventListener: (e,f) => {{ if(e==='DOMContentLoaded'||e==='load') setTimeout(f,10); }}
    }};

    globalScope.window = window;
    globalScope.document = document;
    globalScope.location = window.location;
    globalScope.navigator = window.navigator;

    // --- 4. Interception ---
    function captureAndExit(data, url) {{
        const result = {{ data: data, __url: url }};
        console.log("JSON_START" + JSON.stringify(result) + "JSON_END");
        process.exit(0);
    }}

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
    }}
    globalScope.XMLHttpRequest = XMLHttpRequest;

    // --- 5. Run ---
    globalScope.MOVIE_ID = {config['MOVIE_ID']};
    globalScope.PLAYER_CUID = "{config['PLAYER_CUID']}";
    globalScope.IDENTIFIER = "{config['IDENTIFIER']}";

    try {{
        {hs_code}
    }} catch (e) {{
        console.error("RUNTIME_ERROR: " + e.message);
    }}

    setTimeout(() => {{
        console.error("TIMEOUT_ERROR: Script finished without Ajax call.");
    }}, 6000);
    """

    filename = "runner.js"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(js_payload)

    try:
        result = subprocess.run(["node", filename], capture_output=True, text=True, timeout=8)
        if os.path.exists(filename): os.remove(filename)

        output = result.stdout + result.stderr
        match = re.search(r'JSON_START(.*?)JSON_END', output)
        if match:
            return json.loads(match.group(1)), None
        else:
            return None, output
    except Exception as e:
        return None, str(e)

# ==============================================================================
# 3. Endpoints
# ==============================================================================
@app.route('/')
def home():
    return "Final Scraper Running."

@app.route('/get-json')
def fetch_data():
    config, result = fetch_assets()
    if not result: return jsonify({"status": "error", "message": "Failed fetch"}), 500

    params, error_log = run_node_script(config, result)
    if not params:
        return jsonify({"status": "error", "message": "Signature failed", "debug_log": error_log}), 500

    api_path = params.pop('__url', '/user_data')
    if api_path.startswith("http"): api_url = api_path
    else: api_url = BASE_URL + api_path
    
    req_headers = HEADERS.copy()
    req_headers.update({ "X-Requested-With": "XMLHttpRequest", "Origin": BASE_URL })
    
    try:
        resp = requests.get(api_url, params=params, headers=req_headers, proxies=PROXIES, timeout=20)
        match = re.search(r'(\[.*\])', resp.text, re.DOTALL)
        if match:
            return jsonify({"status": "success", "data": json.loads(match.group(1))})
        else:
            return jsonify({"status": "error", "message": "Invalid response", "raw": resp.text[:200]}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
