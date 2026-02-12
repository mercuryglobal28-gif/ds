from flask import Flask, jsonify
import execjs
import requests
import json
import re
import os

app = Flask(__name__)

# إعدادات ثابتة
BASE_URL = "https://kinovod120226.pro"
MOVIE_ID = 259509
# حاول تحديث هذه القيم يدوياً إذا تغيرت، أو يمكن سحبها بـ requests بسيط (Regex)
PLAYER_CUID = "3cc6fa6dd817a33293536224177e55c4" 
IDENTIFIER = "Kv7l5lK5edlT6ZlYI4Yu"

# بيئة المحاكاة (JS Mock)
JS_ENV = f"""
    var window = {{
        location: {{
            href: '{BASE_URL}/serial/{MOVIE_ID}-predatelstvo',
            hostname: 'kinovod120226.pro',
            protocol: 'https:',
            origin: '{BASE_URL}'
        }},
        navigator: {{ userAgent: 'Mozilla/5.0' }},
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
    
    var MOVIE_ID = {MOVIE_ID};
    var PLAYER_CUID = "{PLAYER_CUID}";
    var IDENTIFIER = "{IDENTIFIER}";

    var captured_params = {{}};
    
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

def get_hs_js_content():
    # محاولة تحميل ملف hs.js من الموقع
    # الرابط قد يتغير، لذا نحاول تخمينه أو نستخدم رابطاً ثابتاً إذا عرفناه
    # عادة يكون: /js/hs.js أو مشابه.
    # للسهولة هنا: يفضل أن ترفع ملف hs.js مع مشروعك وتسميه 'hs.js'
    if os.path.exists("hs.js"):
        with open("hs.js", "r", encoding="utf-8") as f:
            return f.read()
    return None

def run_js_engine():
    hs_code = get_hs_js_content()
    if not hs_code:
        return None, "hs.js file not found"

    full_script = JS_ENV + "\n" + hs_code + "\n" + "function getData(){ return JSON.stringify(captured_params); }"
    
    try:
        # تحديد Node كمحرك تشغيل
        ctx = execjs.get("Node").compile(full_script)
        data_str = ctx.call("getData")
        return json.loads(data_str), None
    except Exception as e:
        return None, str(e)

@app.route('/')
def home():
    return "JS Engine Scraper Running"

@app.route('/get-json')
def fetch_data():
    params, error = run_js_engine()
    
    if error:
        return jsonify({"status": "error", "message": error}), 500
    
    if not params:
        return jsonify({"status": "error", "message": "Failed to generate signature"}), 500

    # إرسال الطلب الحقيقي
    api_url = BASE_URL + params.pop('__url', '/user_data')
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"{BASE_URL}/serial/{MOVIE_ID}",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    try:
        resp = requests.get(api_url, params=params, headers=headers, timeout=10)
        
        # استخراج JSON من الرد
        match = re.search(r'(\[.*\])', resp.text, re.DOTALL)
        if match:
            clean_data = json.loads(match.group(1))
            return jsonify({"status": "success", "data": clean_data})
        else:
            return jsonify({"status": "error", "message": "Invalid response format", "raw": resp.text[:200]}), 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
