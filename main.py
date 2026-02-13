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
# 2. تشغيل Node.js (Eager Execution Environment)
# ==============================================================================
def run_node_script(config, hs_code):
    js_payload = f"""
    const globalScope = typeof global !== 'undefined' ? global : this;

    // --- 1. Interception Logic ---
    function captureAndExit(data, url) {{
        const result = {{
            data: data,
            __url: url
        }};
        console.log("JSON_START" + JSON.stringify(result) + "JSON_END");
        process.exit(0);
    }}

    // --- 2. JQUERY MOCK (Eager Mode) ---
    // هذا الكائن يمثل أي عنصر يتم اختياره بواسطة $
    const JQ_ELEMENT = {{
        length: 1, // هام جداً: نجعل السكربت يظن أن العناصر موجودة
        val: function() {{ return '0'; }},
        text: function() {{ return ''; }},
        attr: function() {{ return ''; }},
        css: function() {{ return ''; }},
        data: function() {{ return {{}}; }},
        prop: function() {{ return false; }},
        width: function() {{ return 1920; }},
        height: function() {{ return 1080; }},
        offset: function() {{ return {{top:0, left:0}}; }},
        index: function() {{ return 0; }},
        
        // التلاعب
        append: function() {{ return this; }},
        appendTo: function() {{ return this; }},
        insertBefore: function() {{ return this; }},
        find: function() {{ return this; }},
        eq: function() {{ return this; }},
        slice: function() {{ return this; }},
        
        // الأحداث
        on: function() {{ return this; }},
        trigger: function() {{ return this; }},
        
        // التكرار: ينفذ الكود مرة واحدة
        each: function(cb) {{
            if (typeof cb === 'function') {{ try {{ cb.call(this, 0, this); }} catch(e){{}} }}
            return this;
        }}
    }};

    // الدالة الرئيسية $
    const $ = function(selector) {{
        // إذا كان دالة (ready)، نفذها فوراً
        if (typeof selector === 'function') {{
            try {{ selector(); }} catch(e) {{ console.error("JQ_READY_ERR: "+e.message); }}
            return;
        }}
        // إذا كان اختيار عنصر، أعد العنصر الوهمي
        return JQ_ELEMENT;
    }};

    // الإضافات
    $.fn = JQ_ELEMENT;
    $.extend = function(target, ...sources) {{ return target || {{}}; }};
    $.rating = function() {{}};
    $.cookie = function() {{}};
    $.isFunction = function(f) {{ return typeof f === 'function'; }};
    
    // Ajax
    $.ajax = function(settings) {{
        if (settings.url && settings.url.indexOf('user_data') !== -1) {{
            captureAndExit(settings.data, settings.url);
        }}
        return {{ done: ()=>{{}}, fail: ()=>{{}} }};
    }};
    $.post = $.ajax;

    // نشر jQuery
    globalScope.$ = $;
    globalScope.jQuery = $;
    
    // --- 3. Browser Objects Mock ---
    const window = {{
        location: {{ href: '{FULL_TARGET_URL}', hostname: 'kinovod120226.pro', origin: '{BASE_URL}', protocol: 'https:', pathname: '{TARGET_URI}', search: '' }},
        navigator: {{ userAgent: '{HEADERS['User-Agent']}', webdriver: false }},
        document: {{ cookie: '' }},
        screen: {{ width: 1920, height: 1080 }},
        localStorage: {{ getItem: ()=>null, setItem: ()=>{{}} }},
        sessionStorage: {{ getItem: ()=>null, setItem: ()=>{{}} }},
        console: console,
        innerWidth: 1920,
        innerHeight: 1080
    }};
    window.window = window;
    window.self = window;
    window.top = window;

    const document = {{
        location: window.location,
        cookie: '',
        referrer: '{BASE_URL}',
        // أي بحث عن عنصر يعيد العنصر الوهمي الذي طوله 1
        getElementById: () => JQ_ELEMENT,
        getElementsByTagName: () => [JQ_ELEMENT],
        querySelector: () => JQ_ELEMENT,
        querySelectorAll: () => [JQ_ELEMENT],
        createElement: () => JQ_ELEMENT,
        documentElement: {{ style: {{}} }},
        body: JQ_ELEMENT,
        // تسجيل الأحداث وتنفيذها فوراً
        addEventListener: (e,f) => {{ if(e==='DOMContentLoaded'||e==='load') f(); }}
    }};

    globalScope.window = window;
    globalScope.document = document;
    globalScope.location = window.location;
    globalScope.navigator = window.navigator;
    globalScope.screen = window.screen;

    // Mock XMLHttpRequest just in case
    globalScope.XMLHttpRequest = class {{
        open(m, u) {{ this.url = u; }}
        send(d) {{
            if (this.url && this.url.includes('user_data')) {{
                 // Simple parser
                 let p = {{}};
                 if(this.url.includes('?')) {{
                     this.url.split('?')[1].split('&').forEach(pair => {{
                         const [k,v] = pair.split('=');
                         p[k] = decodeURIComponent(v||'');
                     }});
                 }}
                 captureAndExit(p, this.url.split('?')[0]);
            }}
        }}
        setRequestHeader() {{}}
    }};

    // --- 4. Variables ---
    globalScope.MOVIE_ID = {config['MOVIE_ID']};
    globalScope.PLAYER_CUID = "{config['PLAYER_CUID']}";
    globalScope.IDENTIFIER = "{config['IDENTIFIER']}";

    // --- 5. Override Timers (Time Travel) ---
    // أي setTimeout يتم تنفيذه فوراً
    const originalSetTimeout = setTimeout;
    global.setTimeout = function(fn, delay) {{
        try {{ fn(); }} catch(e) {{}}
        return 1;
    }};
    global.setInterval = function(fn, delay) {{
        try {{ fn(); }} catch(e) {{}}
        return 1;
    }};

    // --- 6. Run Code ---
    try {{
        {hs_code}
    }} catch (e) {{
        // Log error but don't exit, maybe ajax was queued
        console.error("RUNTIME_EXEC_ERR: " + e.message);
    }}
    
    // Safety check with original timer
    originalSetTimeout(() => {{
        // If we are here, process.exit(0) wasn't called
        console.error("TIMEOUT_ERROR: Script finished without Ajax call.");
    }}, 4000);
    """

    filename = "runner.js"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(js_payload)

    try:
        result = subprocess.run(["node", filename], capture_output=True, text=True, timeout=6)
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
    return "Eager Scraper Running."

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
