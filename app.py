import os
import pandas as pd
from flask import Flask, request
import requests
import google.generativeai as genai
import io
import traceback

app = Flask(__name__)

# --- إعدادات الصفحة الرئيسية ---
@app.route('/')
def home():
    return "Miqdam Bot is Running Successfully!", 200

# --- جلب المفاتيح ---
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# --- الإعداد الذكي للموديل (Auto-Select) ---
if GOOGLE_KEY:
    genai.configure(api_key=GOOGLE_KEY)
    try:
        # نسأل جوجل عن الموديلات المتوفرة
        print("🔍 جاري البحث عن موديل مناسب...")
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        print(f"📋 الموديلات المتاحة: {available_models}")
        
        # نختار الأفضل حسب المتوفر
        if 'models/gemini-1.5-flash' in available_models:
            model_name = 'gemini-1.5-flash'
        elif 'models/gemini-pro' in available_models:
            model_name = 'gemini-pro'
        elif available_models:
            # نختار أول واحد نجده إذا لم نجد المفضلين
            model_name = available_models[0].replace('models/', '')
        else:
            model_name = 'gemini-1.5-flash' # محاولة أخيرة
            
        print(f"✅ تم اختيار الموديل: {model_name}")
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        print(f"⚠️ خطأ في اختيار الموديل: {e}")
        # احتياطياً نستخدم فلاش
        model = genai.GenerativeModel('gemini-1.5-flash')
else:
    print("❌ خطأ: مفتاح جوجل غير موجود في المتغيرات!")

def get_inventory():
    try:
        if not SHEET_URL:
            return "رابط المخزون مفقود."
        response = requests.get(SHEET_URL)
        df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        df['Image URL'] = df['Image URL'].fillna('')
        text = "المخزون:\n"
        for _, row in df.iterrows():
            p_name = row.get('Product Name', row.iloc[0]) 
            p_price = row.get('Price Description', row.iloc[1])
            p_stock = row.get('Stock Status', row.iloc[2])
            text += f"- {p_name} | {p_price} | {p_stock}\n"
        return text
    except:
        return "المخزون قيد التحديث."

def ask_gemini(user_text):
    if not GOOGLE_KEY:
        return "خطأ في النظام (المفتاح مفقود)."
        
    inventory = get_inventory()
    prompt = f"""
    أنت 'هود'، مسؤول المبيعات في 'ورشة المقدام' للخياطة في الجزائر.
    
    شخصيتك:
    -لاتعرف بنفسك الا اذا سألك ما اسمك 
    - عند الحديث لاول مرة رحب به فقط من بعدها لا ترحب اجب مباشرة 
    - تتكلم باللهجة الجزائرية الدارجة (مفهومة ومحترمة).
    - أسلوبك ودود ومشجع (استخدم كلمات مثل: يا خويا، الله يبارك، مرحبا بيك، سلعة شابة).
    - أن يكون كلامك مختصر و مقنع وليس بارد جدا لا تكثر الكلام حاول دائما الاختصار .
    - أنت ذكي في البيع: لا تعطي السعر فقط وتسكت، بل شجع الزبون (مثلاً: "هذا الموديل مطلوب بزاف"، "القماش بارد صيفي").
    
    مهمتك:
    1. الرد على استفسارات الزبائن بلهجة جزائرية مهذبة ومحترفة.
    3. إذا كان المنتج غير متوفر، اقترح بديلاً من القائمة.
    4. حاول إقناع الزبون بذكاء وإغلاق البيع (مثلاً: "الكمية محدودة، شحال تحتاج من حبة؟").
    5. لا تخترع أسعاراً أو منتجات غير موجودة في القائمة.
    6. إذا طلب الزبون صورة (وكان الرابط موجوداً)، اكتب في نهاية الرد: ||IMG:الرابط||
    7. حاول إقناع الزبون بأسلوب لطيف (مثال: "السلعة راهي طير، ما تضيعش الفرصة").
    8.هدفك ليس الدردشة، بل إقناع الزبون بتقديم طلبية
    9.لا تنهِ كلامك بنقطة. دائماً انهِ بسؤال يدفع للشراء
    المخزون: {inventory}
    الزبون: {user_text}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Error Generating: {e}")
        return "اسمحلي خويا، كاين ضغط، عاود ابعثلي."

def send_fb_message(recipient_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    requests.post(url, json=payload)

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
                            reply = ask_gemini(msg)
                            send_fb_message(sid, reply)
            return "ok", 200
        except:
            traceback.print_exc()
            return "ok", 200

if __name__ == '__main__':
    app.run(port=5000)