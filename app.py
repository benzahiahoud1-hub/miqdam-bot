import os
import pandas as pd
from flask import Flask, request
import requests
from groq import Groq
import io
import traceback

app = Flask(__name__)

# --- التحقق من عمل السيرفر ---
@app.route('/')
def home():
    return "✅ Miqdam Bot is Running on Port 10000!", 200

# --- المتغيرات ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# --- إعداد Groq (بشكل آمن) ---
client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        print("✅ Groq Connected Successfully")
    except Exception as e:
        print(f"❌ Error init Groq: {e}")
else:
    print("⚠️ Warning: GROQ_API_KEY is missing")

def get_inventory():
    """جلب المخزون"""
    try:
        if not SHEET_URL:
            return "رابط الشيت مفقود."
        
        # استخدام timeout لتجنب توقف السيرفر اذا كان النت ضعيف
        response = requests.get(SHEET_URL, timeout=10)
        response.raise_for_status()
        
        df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        df.fillna('', inplace=True) 
        
        text = ""
        for _, row in df.iterrows():
            # تأكد من ترتيب الأعمدة: الاسم، السعر، المخزون، رابط الصورة
            p_name = row.get('Product Name', row.iloc[0])
            p_price = row.get('Price', row.iloc[1])
            p_stock = row.get('Stock', row.iloc[2])
            p_img = row.get('Image URL', row.iloc[3])
            
            text += f"المنتج: {p_name} | السعر: {p_price} | الحالة: {p_stock} | الرابط: {p_img}\n"
        return text
    except Exception as e:
        print(f"⚠️ Error reading sheet: {e}")
        return "المخزون غير متوفر حالياً (صيانة)."

def ask_groq(user_text):
    if not client:
        return "السيرفر في حالة صيانة، دقيقة ونرجعو.", None

    inventory_data = get_inventory()
    
    # --- البرومبت الجزائري المحترف ---
    system_instruction = f"""
    أنت 'أمين'، مسير مبيعات في 'ورشة المقدام'.
    
    🛑 شخصيتك:
    - تاجر جملة (Grossiste) محترف، ولد فاميليا، وكلامك "قح" (Pure Algerian).
    - ممنوع الفصحى (No Standard Arabic). تكلم بالدارجة فقط.
    
    🛑 القاموس (Vocabulary):
    - بدل "السعر هو" -> قل: "سومتها"، "نحسبوهالك بـ".
    - بدل "مرحباً" -> قل: "واش خويا"، "السلام عليكم".
    - بدل "حسناً/أجل" -> قل: "بيان سور"، "ما يكون لا خاطرك".
    
    🛑 القواعد:
    1. بيع بالجملة فقط (Gros Only). ارفض التجزئة (Detail) بأدب: "الورشة تبيع غير السيري".
    2. جاوب فقط على المنتج المطلوب.
    3. إذا وجدت رابط صورة، ضعه في النهاية بعد كلمة IMAGE:.
    
    المخزون:
    {inventory_data}
    """

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_text}
            ],
            temperature=0.3,
            max_tokens=200,
        )
        full_response = completion.choices[0].message.content
        
        # استخراج الصورة
        image_url = None
        reply_text = full_response
        
        if "IMAGE:" in full_response:
            parts = full_response.split("IMAGE:")
            reply_text = parts[0].strip()
            if len(parts) > 1:
                potential_url = parts[1].strip()
                if potential_url.startswith("http"):
                    image_url = potential_url.split()[0] # أخذ الرابط الأول فقط
        
        return reply_text, image_url

    except Exception as e:
        print(f"❌ Groq Error: {e}")
        return "اسمحلنا خويا، كاين ضغط، عاود ابعثلي.", None

def send_fb_message(recipient_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    requests.post(url, json=payload)

def send_fb_image(recipient_id, image_url):
    if not image_url: return
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {
                    "url": image_url, 
                    "is_reusable": True
                }
            }
        }
    }
    try:
        r = requests.post(url, json=payload)
        if r.status_code != 200:
            print(f"⚠️ FB Image Fail: {r.text}")
    except Exception as e:
        print(f"⚠️ FB Image Error: {e}")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Verification Failed", 403

    if request.method == 'POST':
        try:
            data = request.json
            if data.get('object') == 'page':
                for entry in data['entry']:
                    for event in entry.get('messaging', []):
                        if 'message' in event and 'text' in event['message']:
                            sender_id = event['sender']['id']
                            user_msg = event['message']['text']
                            
                            if event['message'].get('is_echo'):
                                continue
                            
                            reply_text, reply_image = ask_groq(user_msg)
                            send_fb_message(sender_id, reply_text)
                            if reply_image:
                                send_fb_image(sender_id, reply_image)
            return "ok", 200
        except Exception:
            traceback.print_exc()
            return "ok", 200

# --- 🔴 التعديل الحاسم لحل مشكلة Port Timeout 🔴 ---
if __name__ == '__main__':
    # الحصول على البورت من Render أو استخدام 10000 كاحتياط
    port = int(os.environ.get("PORT", 10000))
    # host='0.0.0.0' ضروري جداً ليعمل على السيرفر
    app.run(host='0.0.0.0', port=port)