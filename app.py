import os
import pandas as pd
from flask import Flask, request
import requests
from groq import Groq
import io
import traceback

app = Flask(__name__)

# --- الصفحة الرئيسية للتأكد من عمل السيرفر ---
@app.route('/')
def home():
    return "✅ Miqdam Bot (Llama 3.3 Edition) is Live!", 200

# --- جلب المفاتيح من متغيرات البيئة ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# --- إعداد عميل Groq ---
try:
    if GROQ_API_KEY:
        client = Groq(api_key=GROQ_API_KEY)
        print("✅ تم إعداد Groq Client بنجاح")
    else:
        client = None
        print("❌ تحذير: مفتاح GROQ_API_KEY مفقود!")
except Exception as e:
    client = None
    print(f"❌ خطأ في إعداد Groq: {e}")

def get_inventory():
    """جلب المخزون من شيت جوجل وتنسيقه للنص"""
    try:
        if not SHEET_URL:
            return "رابط المخزون غير موجود في الإعدادات."
            
        response = requests.get(SHEET_URL)
        response.raise_for_status()
        
        # قراءة ملف CSV
        df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        
        # تحويل البيانات إلى نص مفهوم للذكاء الاصطناعي
        text = "📦 **قائمة المخزون الحالية:**\n"
        for _, row in df.iterrows():
            # تأكد أن أسماء الأعمدة هنا تطابق ملفك (أو استخدم row.iloc[0] للأمان)
            p_name = row.get('Product Name', row.iloc[0]) 
            p_price = row.get('Price', row.iloc[1]) 
            p_stock = row.get('Stock', row.iloc[2]) 
            text += f"- {p_name} | السعر: {p_price} | الحالة: {p_stock}\n"
        return text
    except Exception as e:
        print(f"⚠️ خطأ في قراءة الشيت: {e}")
        return "المخزون غير متاح حالياً."

def ask_groq(user_text):
    """إرسال الرسالة إلى Groq Llama 3.3"""
    if not client:
        return "نعتذر، الخدمة متوقفة مؤقتاً (خطأ في الإعدادات)."
        
    inventory_data = get_inventory()
    
    # --- تعليمات البوت (System Prompt) ---
    system_instruction = f"""
    أنت 'أمين'، البائع المحترف في 'ورشة المقدام'.
    
    التعليمات:
    1. لهجتك جزائرية، مهذبة، ومختصرة.
    2. الورشة تبيع **بالجملة فقط** (Gros). ارفض البيع بالتجزئة (Detail) بلباقة.
    3. اعتمد على القائمة أدناه للأسعار.
    4. إذا المنتج غير موجود، قل: "ماكانش متوفر حالياً".
    
    المخزون:
    {inventory_data}
    """

    try:
        completion = client.chat.completions.create(
            # 👇 تم تحديث الموديل هنا إلى النسخة الشغالة
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_text}
            ],
            temperature=0.3, # ليكون دقيقاً في الأسعار
            max_tokens=250,  # طول الرد
        )
        return completion.choices[0].message.content
    except Exception as e:
        # طباعة الخطأ الحقيقي في السجلات لنعرف السبب
        print(f"❌ Groq API Error: {e}")
        
        # رسالة لطيفة للزبون بدل الخطأ التقني
        return "اسمحلنا خويا، كاين ضغط صغير، عاود ابعثلي درك نجاوبك."

def send_fb_message(recipient_id, text):
    """إرسال الرد إلى ماسنجر"""
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    try:
        r = requests.post(url, json=payload)
        if r.status_code != 200:
            print(f"⚠️ فشل إرسال الرسالة: {r.text}")
    except Exception as e:
        print(f"⚠️ خطأ اتصال بفيسبوك: {e}")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # التحقق من الـ Token (لربط فيسبوك أول مرة)
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
                            sender_id = event['sender']['id']
                            message_text = event['message']['text']
                            
                            # تجاهل رسائل البوت نفسه (Echo)
                            if event['message'].get('is_echo'):
                                continue
                                
                            # الحصول على الرد وإرساله
                            reply = ask_groq(message_text)
                            send_fb_message(sender_id, reply)
            return "ok", 200
        except Exception:
            traceback.print_exc()
            return "ok", 200

if __name__ == '__main__':
    app.run(port=5000)