import os
import pandas as pd
from flask import Flask, request
import requests
import google.generativeai as genai
import io
import traceback

app = Flask(__name__)

# ====================================================
# 1. إعدادات السيرفر والمفاتيح (تُجلب من Render)
# ====================================================

# مفاتيح النظام
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# إعدادات نموذج حفظ الطلبات (يجب إضافتها في Render لاحقاً)
# الرابط يجب أن ينتهي بـ /formResponse
FORM_URL = os.environ.get("FORM_URL") 
# أسماء الحقول السرية (entry.xxxx)
ENTRY_NAME = os.environ.get("ENTRY_NAME")   
ENTRY_ORDER = os.environ.get("ENTRY_ORDER") 
ENTRY_PHONE = os.environ.get("ENTRY_PHONE") 

# ====================================================
# 2. إعداد الذكاء الاصطناعي (اختيار الموديل تلقائياً)
# ====================================================
if GOOGLE_KEY:
    genai.configure(api_key=GOOGLE_KEY)
    try:
        # البحث عن الموديل المناسب
        print("🔍 جاري ضبط Gemini...")
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        if 'models/gemini-1.5-flash' in available_models:
            model_name = 'gemini-1.5-flash'
        elif 'models/gemini-pro' in available_models:
            model_name = 'gemini-pro'
        else:
            model_name = 'gemini-1.5-flash'
            
        print(f"✅ تم تفعيل الموديل: {model_name}")
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        print(f"⚠️ خطأ في الموديل: {e}")
        model = genai.GenerativeModel('gemini-1.5-flash')

# ====================================================
# 3. الوظائف المساعدة (جلب المخزون + حفظ الطلب)
# ====================================================

def get_inventory():
    """جلب قائمة السلع من Google Sheet"""
    try:
        if not SHEET_URL:
            return "رابط المخزون مفقود."
        response = requests.get(SHEET_URL)
        df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        df['Image URL'] = df['Image URL'].fillna('')
        text = "المخزون المتوفر:\n"
        for _, row in df.iterrows():
            p_name = row.get('Product Name', row.iloc[0]) 
            p_price = row.get('Price Description', row.iloc[1])
            p_stock = row.get('Stock Status', row.iloc[2])
            text += f"- {p_name} | {p_price} | {p_stock}\n"
        return text
    except:
        return "المخزون قيد التحديث."

def save_order_to_sheet(name, order, phone):
    """إرسال الطلب إلى Google Form ليظهر في الشيت"""
    if not FORM_URL:
        print("❌ رابط الفورم غير موجود!")
        return False
    
    try:
        # تجهيز البيانات
        form_data = {
            ENTRY_NAME: name,
            ENTRY_ORDER: order,
            ENTRY_PHONE: phone
        }
        # الإرسال
        response = requests.post(FORM_URL, data=form_data)
        if response.status_code == 200:
            print(f"✅ تم حفظ طلب {name} بنجاح!")
            return True
        else:
            print(f"❌ فشل الحفظ. الرمز: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ خطأ أثناء الحفظ: {e}")
        return False

def ask_gemini(user_text):
    """عقل البوت (شخصية هود)"""
    if not GOOGLE_KEY:
        return "خطأ: المفتاح مفقود."
        
    inventory = get_inventory()
    
    # --- شخصية هود (بائع الجملة الصارم) ---
    prompt = f"""
    أنت 'أمين'، مسؤول المبيعات في 'ورشة المقدام' للخياطة في الجزائر.
    
    شخصيتك:
    - تتكلم باللهجة الجزائرية الدارجة (مفهومة ومحترمة).
    - أسلوبك ودود ومشجع (استخدم كلمات مثل: يا خويا، الله يبارك، مرحبا بيك، سلعة شابة).
    - أنت ذكي في البيع: لا تعطي السعر فقط وتسكت، بل شجع الزبون (مثلاً: "هذا الموديل مطلوب بزاف"، "القماش بارد صيفي").
    
    تعليمات الأسعار:
    - المعلومات موجودة في القائمة أدناه. اقرأ تفاصيل السعر جيداً قبل الرد.
    - إذا كان هناك سعر للجملة وسعر للتجزئة، وضح الفرق للزبون لتشجيعه على الجملة.
    
    قائمة المنتجات الحالية:
    {inventory}

    رسالة الزبون: {user_text}
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Error: {e}")
        return "الشبكة راهي ثقيلة، عاود خويا."

def send_fb_message(recipient_id, text):
    """إرسال الرد إلى فيسبوك"""
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    requests.post(url, json=payload)

# ====================================================
# 4. نقطة الاتصال (Webhook)
# ====================================================

@app.route('/')
def home():
    return "Miqdam Bot (Hood Edition) is Live!", 200

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
                            
                            # 1. الحصول على الرد من هود
                            reply = ask_gemini(msg)
                            
                            # 2. فحص هل يوجد طلب للحفظ؟
                            if "||SAVE||" in reply:
                                try:
                                    # استخراج البيانات ما بين العلامات
                                    parts = reply.split("||SAVE||")[1].split("||")[0].split("|")
                                    if len(parts) >= 3:
                                        c_name = parts[0].strip()
                                        c_order = parts[1].strip()
                                        c_phone = parts[2].strip()
                                        
                                        # حفظ في الشيت (عبر الفورم)
                                        save_order_to_sheet(c_name, c_order, c_phone)
                                    
                                    # تنظيف الرسالة (حذف الكود السري) قبل إرسالها للزبون
                                    reply = reply.split("||SAVE||")[0]
                                except Exception as e:
                                    print(f"خطأ في معالجة الطلب: {e}")

                            # 3. إرسال الرد النظيف للزبون
                            send_fb_message(sid, reply)
            return "ok", 200
        except:
            traceback.print_exc()
            return "ok", 200

if __name__ == '__main__':
    app.run(port=5000)