import os
import pandas as pd
from flask import Flask, request
import requests
import google.generativeai as genai
import io
import traceback

app = Flask(__name__)

# --- صفحة البداية (للتأكد أن السيرفر يعمل) ---
@app.route('/')
def home():
    return "Miqdam Bot (Hood Edition) is Running!", 200

# ====================================================
# 1. جلب المفاتيح
# ====================================================
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# ====================================================
# 2. إعداد الذكاء الاصطناعي (سريع ومستقر)
# ====================================================
if GOOGLE_KEY:
    genai.configure(api_key=GOOGLE_KEY)
    try:
        # نستخدم gemini-1.5-flash مباشرة لتجنب تأخير التشغيل ومشاكل Render
        model = genai.GenerativeModel('gemini-1.5-flash')
        print("✅ تم تفعيل الموديل: gemini-1.5-flash")
    except Exception as e:
        print(f"⚠️ خطأ في إعداد الموديل: {e}")
else:
    print("❌ خطأ: مفتاح جوجل غير موجود!")

# ====================================================
# 3. الوظائف المساعدة
# ====================================================

def get_inventory():
    """جلب المخزون من الشيت"""
    try:
        if not SHEET_URL:
            return "رابط المخزون مفقود."
        # timeout=10 مهم جداً لكي لا يتجمد البوت إذا كان النت ضعيفاً
        response = requests.get(SHEET_URL, timeout=10)
        df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        df['Image URL'] = df['Image URL'].fillna('')
        text = "المخزون المتوفر (بيع جملة فقط):\n"
        for _, row in df.iterrows():
            p_name = row.get('Product Name', row.iloc[0]) 
            p_price = row.get('Price Description', row.iloc[1])
            p_stock = row.get('Stock Status', row.iloc[2])
            text += f"- {p_name} | {p_price} | {p_stock}\n"
        return text
    except:
        return "المخزون قيد التحديث."

def ask_gemini(user_text):
    """عقل البوت (شخصية هود الصارمة)"""
    if not GOOGLE_KEY:
        return "خطأ: مفتاح النظام مفقود."
        
    inventory = get_inventory()
    
    # --- البرومبت: هود (بدون حفظ طلبات) ---
    prompt = f"""
    الشخصية: أنت 'هود'، بائع جملة (Grossiste) في ورشة المقدام.
    الصفات: بائع جزائري "قافز"، عملي، هدرتك قليلة ومفيدة (Direct)، ما تهدرش كي الروبوت.
    اللهجة: جزائرية 100% (سوق الجملة). استخدم كلمات مثل: (السومة، كاين، ماكاش، ديسپو).

    قواعد التعامل الصارمة:
    1. **الجملة فقط:** ممنوع منعاً باتاً تبيع "الحبة" (Détail). إذا طلب حبة قل له بعبارة واحدة: "اسمحلنا خوي، الورشة تخدم غير بالجملة".
    2. **السعر المباشر:** إذا سأل عن السعر، أعطه السعر فوراً من المخزون، لا تتهرب ولا تقل "تعال للخاص". قل: "السعر كذا للحبة، والمينيموم كذا حبات".
    3. **الاختصار:** لا تكثر الترحيب والمقدمات الطويلة. جاوب على قد السؤال.
    4. **الهدف:** البيع والإقناع بسرعة.

    المخزون الحالي (الأسعار والكميات):
    {inventory}

    سيناريوهات للأجوبة (أمثلة لأسلوبك):
    - الزبون: "غالية شوية.."
      ردك: "يا ودي سلعة فينيسيون وتستاهل، تربح فيها الخير والبركة. السلعة شابة ما تندمش."
      
    - الزبون: "عندكم بيع بالحبة؟"
      ردك: "لالا خوي، حنا ورشة نخدمو غير السيري (Gros)."

    رسالة الزبون الحالية: {user_text}
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Error Generating: {e}")
        return "الشبكة راهي ثقيلة شوية، عاود ابعثلي."

def send_fb_message(recipient_id, text):
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
        requests.post(url, json=payload, timeout=10)
    except:
        pass

# ====================================================
# 4. نقطة الاتصال (Webhook)
# ====================================================
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
                            
                            # الرد المباشر (بدون حفظ)
                            reply = ask_gemini(msg)
                            send_fb_message(sid, reply)
            return "ok", 200
        except:
            traceback.print_exc()
            return "ok", 200

if __name__ == '__main__':
    app.run(port=5000)