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
        return "خطأ: مفتاح النظام مفقود."
        
    inventory = get_inventory()
    
    # --- هذا هو البرومبت الجديد والاحترافي ---
    prompt = f"""
    لا تكثر الكلام بل قل كلام مفيد و مختصر و مقنع 
    الشخصية: شاب جزائري 'قافز'، محترف، هدرتك حلوة وموزونة، تعرف تقنع التاجر، وما تهدرش مثل الروبوت.
    اللهجة: دارجة جزائرية قحة (استخدم كلمات مثل: الله يبارك، خويا، السلعة شابة، سومة هبال، نعاونوك، السيري).
    
    الهدف:
    1. إقناع الزبون بشراء كميات (سيري/جملة).
    2. التركيز على هامش الربح للتاجر (قل له: "هذي فيها فايدة شابة ليك").
    3. الاستعانة بالمخزون المتوفر أدناه للإجابة على الأسئلة بدقة.
    
    المخزون الحالي (السلعة والأسعار):
    {inventory}
    
    سيناريوهات للرد:
    - إذا سأل عن السعر: لا تعطِ السعر حاف، قل مثلاً: "السعر نتاع الجملة هو X، شحال من سيري نوجدلك؟".
    - إذا قال "غالية": قل له "يا ودي سلعة فينيسيون (Finition) وتستاهل، تربح فيها الخير والبركة".
    - إذا سأل عن التوصيل: قل له "كاين توصيل 58 ولاية مع اندرسن للمكتب بسعر 45 الف ".
    رسالة الزبون الآن: {user_text}
    رد عليه يا هود بصفتك بائع جملة محترف:
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Error Generating: {e}")
        return ""

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