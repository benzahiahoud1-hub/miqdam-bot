import os
import pandas as pd
from flask import Flask, request
import requests
import google.generativeai as genai
import io
import traceback

app = Flask(__name__)

# ====================================================
# 1. إعدادات السيرفر (Render)
# ====================================================

# مفاتيح النظام الأساسية
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# مفاتيح حفظ الطلبات (سنضيفها في Render)
FORM_URL = os.environ.get("FORM_URL")
ENTRY_NAME = os.environ.get("ENTRY_NAME")
ENTRY_ORDER = os.environ.get("ENTRY_ORDER")
ENTRY_PHONE = os.environ.get("ENTRY_PHONE")

# ====================================================
# 2. إعداد الذكاء الاصطناعي (الحل المستقر)
# ====================================================
if GOOGLE_KEY:
    genai.configure(api_key=GOOGLE_KEY)
    # هنا نستخدم النسخة المستقرة 1.5 لمنع الأخطاء
    model = genai.GenerativeModel('gemini-2.5-pro')
    print("✅ تم تثبيت الموديل المستقر: gemini-2.5-pro")
else:
    print("❌ خطأ: مفتاح جوجل مفقود")

# ====================================================
# 3. الوظائف (المخزون + الحفظ + الذكاء)
# ====================================================

def get_inventory():
    """جلب المخزون للقراءة فقط"""
    try:
        if not SHEET_URL:
            return "رابط المخزون مفقود."
        response = requests.get(SHEET_URL)
        df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        df['Image URL'] = df['Image URL'].fillna('')
        text = "المخزون المتوفر (للبائع فقط):\n"
        for _, row in df.iterrows():
            p_name = row.get('Product Name', row.iloc[0]) 
            p_price = row.get('Price Description', row.iloc[1])
            p_stock = row.get('Stock Status', row.iloc[2])
            text += f"- {p_name} | {p_price} | {p_stock}\n"
        return text
    except:
        return "المخزون قيد التحديث."

def save_order_to_sheet(name, order, phone):
    """إرسال البيانات للنموذج ليحفظها في الشيت"""
    if not FORM_URL:
        print("⚠️ تنبيه: لم يتم إعداد رابط الفورم في Render")
        return False
    
    try:
        # تعبئة البيانات
        form_data = {
            ENTRY_NAME: name,
            ENTRY_ORDER: order,
            ENTRY_PHONE: phone
        }
        # إرسال
        requests.post(FORM_URL, data=form_data)
        print(f"✅ تم حفظ طلب {name} بنجاح!")
        return True
    except Exception as e:
        print(f"❌ فشل الحفظ: {e}")
        return False

def ask_gemini(user_text):
    """عقل هود (الصارم)"""
    if not GOOGLE_KEY:
        return "خطأ تقني في النظام."
        
    inventory = get_inventory()
    
    prompt = f"""
    أنت 'هود'، بائع جملة (Grossiste) في ورشة المقدام.
    الشخصية: بائع جزائري "قافز"، عملي، كلامك قليل ومفيد، ما تحبش تكسار الراس.
    اللهجة: دارجة جزائرية تع السوق (Gros, Série, Affaire, Dispo).

    قواعدك الصارمة:
    1. **الجملة فقط:** ممنوع تبيع الحبة (Détail). إذا طلب حبة قل له: "نخدمو غير السيري خويا".
    2. **الأسلوب:** لا ترحب كثيراً. ادخل في السعر والكمية مباشرة.
    3. **الهدف:** الاتفاق على البيعة (Closing).

    نظام حفظ الطلب (مهم جداً):
    - إذا أعطاك الزبون معلوماته (الاسم + الطلب + الهاتف) واتفقتم.
    - اكتب في **آخر سطر** من رسالتك هذا الكود السري بالضبط:
    ||SAVE||الاسم|الطلب|الهاتف||
    
    مثال:
    الزبون: "خلاص خويا هود، ديرلي 5 سيري، أنا يوسف من العاصمة 0550..."
    ردك: "خلاص خويا يوسف، سلعتك محجوزة وتوصلك غدوة مع ياليدين. بصحتك.
    ||SAVE||يوسف|5 سيري|0550...||"

    المخزون:
    {inventory}

    الزبون: {user_text}
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Error Generating: {e}")
        # رسالة خطأ بسيطة في حال توقف جوجل
        return "الشبكة راهي ثقيلة شوية، دقيقة وعاود ابعثلي."

def send_fb_message(recipient_id, text):
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    requests.post(url, json=payload)

# ====================================================
# 4. نقطة الاتصال (Webhook)
# ====================================================

@app.route('/')
def home():
    return "Miqdam Bot (Hood Edition) is Ready!", 200

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
                            
                            # 2. فحص هل يوجد كود حفظ؟
                            if "||SAVE||" in reply:
                                try:
                                    parts = reply.split("||SAVE||")[1].split("||")[0].split("|")
                                    if len(parts) >= 3:
                                        c_name = parts[0].strip()
                                        c_order = parts[1].strip()
                                        c_phone = parts[2].strip()
                                        save_order_to_sheet(c_name, c_order, c_phone)
                                    
                                    # تنظيف الرسالة للزبون
                                    reply = reply.split("||SAVE||")[0]
                                except:
                                    pass # استمرار حتى لو فشل الحفظ

                            # 3. إرسال الرد
                            send_fb_message(sid, reply)
            return "ok", 200
        except:
            traceback.print_exc()
            return "ok", 200

if __name__ == '__main__':
    app.run(port=5000)