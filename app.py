import os
import pandas as pd
from flask import Flask, request
import requests
from groq import Groq  # استدعاء مكتبة Groq
import io
import traceback

app = Flask(__name__)

# --- إعدادات الصفحة الرئيسية ---
@app.route('/')
def home():
    return "✅ Miqdam Bot (Groq Edition) is Running!", 200

# --- المتغيرات البيئية ---
# تأكد من وضع مفتاح Groq هنا
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# --- إعداد عميل Groq ---
if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)
    print("✅ تم الاتصال بـ Groq بنجاح")
else:
    print("❌ خطأ: مفتاح GROQ_API_KEY غير موجود!")
    client = None

def get_inventory():
    """جلب المخزون من شيت جوجل"""
    try:
        if not SHEET_URL:
            return "رابط المخزون مفقود."
        response = requests.get(SHEET_URL)
        response.raise_for_status() # التأكد من صحة الرابط
        df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        
        # تنسيق النص ليفهمه الذكاء الاصطناعي بسهولة
        text = "📦 قائمة المنتجات والمخزون الحالي:\n"
        for _, row in df.iterrows():
            # تأكد أن أسماء الأعمدة في الشيت مطابقة لهذه الأسماء أو عدلها هنا
            p_name = row.get('Product Name', row.iloc[0]) 
            p_price = row.get('Price', row.iloc[1]) # السعر
            p_stock = row.get('Stock', row.iloc[2]) # الحالة (متوفر/غير متوفر)
            text += f"- المنتج: {p_name} | السعر: {p_price} | الحالة: {p_stock}\n"
        return text
    except Exception as e:
        print(f"⚠️ خطأ في جلب الشيت: {e}")
        return "المخزون غير متاح حالياً، يرجى سؤال البائع مباشرة."

def ask_groq(user_text):
    """دالة التحدث مع الذكاء الاصطناعي"""
    if not client:
        return "نعتذر، الخدمة متوقفة مؤقتاً للصيانة."
        
    inventory = get_inventory()
    
    # --- البرومبت (System Prompt) ---
    # هنا نعطي الشخصية والتعليمات الصارمة للبوت
    system_instruction = f"""
    أنت 'أمين'، مسؤول المبيعات في 'ورشة المقدام' للخياطة والملابس الجاهزة في الجزائر.
    
    معلوماتك وتعليماتك الصارمة:
    1. **اللهجة:** تكلم بلهجة جزائرية مهذبة ومختصرة (مثال: "مرحبا خويا"، "تفضلي أختي"، "الله يحفظك").
    2. **طبيعة البيع:** الورشة تبيع **بالجملة فقط** (Wholesale).
    3. **قاعدة الرفض:** إذا طلب الزبون "حبة" أو "ديتاي"، اعتذر منه بلباقة وقل: "اسمحلنا خويا/أختي، ورشة المقدام تخدم غير بالجملة (سيري كاملة)".
    4. **الأسعار:** إذا سأل عن السعر، استخرجه بدقة من القائمة أدناه. إذا لم يكن المنتج في القائمة، قل أنك ستتأكد وتعود إليه.
    5. **الأسلوب:** لا تكن ثرثاراً مثل الروبوت. كن عملياً ومباشراً. أعط السعر والمعلومة فوراً.
    
    البيانات الحالية للمخزون والأسعار:
    {inventory}
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": system_instruction
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ],
            model="llama3-70b-8192", # هذا الموديل ممتاز ويدعم العربية واللهجات بقوة
            temperature=0.3, # درجة حرارة منخفضة ليكون دقيقاً في الأسعار ولا يؤلف
            max_tokens=200,  # ردود قصيرة ومفيدة
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"❌ Error Groq: {e}")
        return "اسمحلنا خويا، كاين ضغط على الشبكة، عاود ابعثلي درك نجاوبك."

def send_fb_message(recipient_id, text):
    """إرسال الرد إلى ماسنجر"""
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    try:
        r = requests.post(url, json=payload)
        if r.status_code != 200:
            print(f"⚠️ FB Send Error: {r.text}")
    except Exception as e:
        print(f"⚠️ Connection Error: {e}")

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
                            sid = event['sender']['id']
                            msg = event['message']['text']
                            
                            # لا ترد على رسائلك الخاصة (echo)
                            if event['message'].get('is_echo'):
                                continue
                                
                            # معالجة الرد
                            reply = ask_groq(msg)
                            send_fb_message(sid, reply)
            return "ok", 200
        except Exception:
            traceback.print_exc()
            return "ok", 200

if __name__ == '__main__':
    app.run(port=5000)