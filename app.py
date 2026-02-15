import os
import pandas as pd
from flask import Flask, request
import requests
import google.generativeai as genai
import io
import traceback

app = Flask(__name__)

# --- جلب المفاتيح من إعدادات السيرفر (Render) ---
# لا نضع المفاتيح هنا مباشرة للحماية
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# إعداد Gemini
if GOOGLE_KEY:
    genai.configure(api_key=GOOGLE_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

def get_inventory():
    try:
        if not SHEET_URL:
            return "رابط المخزون غير موجود."
        response = requests.get(SHEET_URL)
        df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        df['Image URL'] = df['Image URL'].fillna('')
        text = "المخزون المتوفر:\n"
        for _, row in df.iterrows():
            # استخدام .get لتجنب الأخطاء إذا تغيرت أسماء الأعمدة
            p_name = row.get('Product Name', row.iloc[0]) 
            p_price = row.get('Price Description', row.iloc[1])
            p_stock = row.get('Stock Status', row.iloc[2])
            text += f"- {p_name} | {p_price} | {p_stock}\n"
        return text
    except:
        traceback.print_exc()
        return "المخزون قيد التحديث."

def ask_gemini(user_text):
    if not GOOGLE_KEY:
        return "خطأ: مفتاح جوجل غير موجود في السيرفر."
        
    inventory = get_inventory()
    prompt = f"""
    أنت 'أمين'، بائع في 'ورشة المقدام'. مهمتك البيع والرد بلهجة جزائرية.
    المخزون الحالي: {inventory}
    رسالة الزبون: {user_text}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error: {e}")
        return "اسمحلي خويا، كاين ضغط على الشبكة."

def send_fb_message(recipient_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    requests.post(url, json=payload)

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # التحقق من فيسبوك
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Verification Failed", 403

    # استقبال الرسائل
    if request.method == 'POST':
        try:
            data = request.json
            if data.get('object') == 'page':
                for entry in data['entry']:
                    for event in entry.get('messaging', []):
                        if 'message' in event and 'text' in event['message']:
                            sid = event['sender']['id']
                            msg = event['message']['text']
                            
                            # الرد
                            reply = ask_gemini(msg)
                            send_fb_message(sid, reply)
            return "ok", 200
        except Exception as e:
            traceback.print_exc()
            return "ok", 200

if __name__ == '__main__':
    app.run(port=5000)