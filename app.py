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
    return "Miqdam Bot (Hood Edition) is Running!", 200

# ====================================================
# 1. جلب المفاتيح (تمت إضافة مفاتيح الفورم)
# ====================================================
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# --- مفاتيح نموذج حفظ الطلبات (جديد) ---
FORM_URL = os.environ.get("FORM_URL")       # رابط الفورم (ينتهي بـ formResponse)
ENTRY_NAME = os.environ.get("ENTRY_NAME")   # رقم حقل الاسم
ENTRY_ORDER = os.environ.get("ENTRY_ORDER") # رقم حقل الطلب
ENTRY_PHONE = os.environ.get("ENTRY_PHONE") # رقم حقل الهاتف

# ====================================================
# 2. الإعداد الذكي للموديل (الكود الخاص بك)
# ====================================================
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
            model_name = available_models[0].replace('models/', '')
        else:
            model_name = 'gemini-1.5-flash' # محاولة أخيرة
            
        print(f"✅ تم اختيار الموديل: {model_name}")
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        print(f"⚠️ خطأ في اختيار الموديل: {e}")
        model = genai.GenerativeModel('gemini-1.5-flash')
else:
    print("❌ خطأ: مفتاح جوجل غير موجود في المتغيرات!")

# ====================================================
# 3. الوظائف المساعدة (جلب المخزون + حفظ الطلب)
# ====================================================

def get_inventory():
    try:
        if not SHEET_URL:
            return "رابط المخزون مفقود."
        response = requests.get(SHEET_URL)
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

def save_order_to_sheet(name, order, phone):
    """(وظيفة جديدة) إرسال الطلب إلى Google Form"""
    if not FORM_URL:
        print("⚠️ رابط الفورم غير مضاف في Render")
        return False
    
    try:
        form_data = {
            ENTRY_NAME: name,
            ENTRY_ORDER: order,
            ENTRY_PHONE: phone
        }
        response = requests.post(FORM_URL, data=form_data)
        if response.status_code == 200:
            print(f"✅ تم حفظ طلب {name} بنجاح!")
            return True
        else:
            print("❌ فشل إرسال الطلب للنموذج.")
            return False
    except Exception as e:
        print(f"❌ خطأ في الاتصال بالفورم: {e}")
        return False

def ask_gemini(user_text):
    if not GOOGLE_KEY:
        return "خطأ في النظام (المفتاح مفقود)."
        
    inventory = get_inventory()
    
    # --- شخصية هود (بائع الجملة الصارم) ---
    prompt = f"""
    الدور: أنت 'هود'، مدير المبيعات في 'ورشة المقدام'.
    الشخصية: بائع جملة (Grossiste) محترف، "قافز"، عملي، كلامك قليل ومفيد (Direct).
    اللهجة: جزائرية قحة (سوق الجملة). استخدم: (Gros, Série, Affaire, Dispo, C'est bon).

    القواعد الصارمة:
    1. **الجملة فقط:** ممنوع تبيع بالقطعة (Détail). إذا طلب حبة قل بصرامة وأدب: "نخدمو غير السيري خويا/أختي".
    2. **الأسلوب:** لا تكثر الترحيب. ادخل في السعر والكمية مباشرة.
    3. **الهدف:** إتمام الصفقة (Closing).

    نظام حفظ الطلب (مهم جداً):
    - إذا أعطاك الزبون معلوماته (الاسم + الطلب + الهاتف) واتفقتم على البيعة.
    - اكتب في **آخر سطر** من رسالتك هذا الكود السري بالضبط:
    ||SAVE||الاسم|الطلب|الهاتف||
    
    مثال:
    الزبون: "خلاص خويا هود، ديرلي 10 سيري، أنا كريم من سطيف 0550..."
    ردك: "خلاص خويا كريم، سلعتك راهي محجوزة. غدوة نبعثوها.
    ||SAVE||كريم|10 سيري|0550...||"

    المخزون الحالي:
    {inventory}

    رسالة الزبون: {user_text}
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Error Generating: {e}")
        return "الشبكة راهي ثقيلة، عاود ابعثلي."

def send_fb_message(recipient_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    requests.post(url, json=payload)

# ====================================================
# 4. Webhook (مع إضافة كشف كود الحفظ)
# ====================================================
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
                            
                            # 1. الحصول على الرد من هود
                            reply = ask_gemini(msg)
                            
                            # 2. (جديد) فحص هل يوجد كود حفظ؟
                            if "||SAVE||" in reply:
                                try:
                                    # استخراج البيانات ما بين العلامات
                                    parts = reply.split("||SAVE||")[1].split("||")[0].split("|")
                                    if len(parts) >= 3:
                                        c_name = parts[0].strip()
                                        c_order = parts[1].strip()
                                        c_phone = parts[2].strip()
                                        
                                        # حفظ في الشيت
                                        save_order_to_sheet(c_name, c_order, c_phone)
                                    
                                    # تنظيف الرسالة (حذف الكود السري لكي لا يراه الزبون)
                                    reply = reply.split("||SAVE||")[0]
                                except:
                                    pass # نكمل عادي حتى لو فشل الحفظ

                            # 3. إرسال الرد للزبون
                            send_fb_message(sid, reply)
            return "ok", 200
        except:
            traceback.print_exc()
            return "ok", 200

if __name__ == '__main__':
    app.run(port=5000)