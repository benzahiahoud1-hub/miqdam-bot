import os
import pandas as pd
from flask import Flask, request
import requests
from groq import Groq
import io
import traceback

app = Flask(__name__)

# --- الصفحة الرئيسية ---
@app.route('/')
def home():
    return "✅ Miqdam Bot (100% DZ) is Running!", 200

# --- المتغيرات ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# --- إعداد Groq ---
client = None
if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"Error init Groq: {e}")

def get_inventory():
    """جلب المخزون وتجهيزه"""
    try:
        if not SHEET_URL:
            return "رابط الشيت مفقود."
        response = requests.get(SHEET_URL)
        response.raise_for_status()
        
        df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        df.fillna('', inplace=True) 
        
        # تجهيز النص للذكاء الاصطناعي
        text = ""
        for _, row in df.iterrows():
            # تأكد من ترتيب الأعمدة في ملفك: الاسم، السعر، المخزون، رابط الصورة
            p_name = row.get('Product Name', row.iloc[0])
            p_price = row.get('Price', row.iloc[1])
            p_stock = row.get('Stock', row.iloc[2])
            p_img = row.get('Image URL', row.iloc[3]) 
            
            # نكتب الرابط بوضوح لكي يراه الذكاء الاصطناعي
            text += f"المنتج: {p_name} | السعر: {p_price} | الحالة: {p_stock} | الرابط: {p_img}\n"
        return text
    except Exception as e:
        print(f"⚠️ Error reading sheet: {e}")
        return "المخزون غير متوفر."

def ask_groq(user_text):
    if not client:
        return "كاين خلل تقني خويا، دقيقة ونرجعولك.", None

    inventory_data = get_inventory()
    
    # --- 🔴 البرومبت الجزائري الاحترافي (V2) 🔴 ---
    system_instruction = f"""
    أنت 'أمين'، مسير مبيعات في 'ورشة المقدام'.
    
    🛑 شخصيتك (Profile):
    - أنت تاجر جملة (Grossiste) محترف، "ولد فاميليا"، وكلامك موزون.
    - لهجتك: جزائرية عاصمة/وسط (Algiers Dialect) نقية.
    - أسلوبك: مباشر، عملي، ومحترم (Professional & Street Smart).
    
    🛑 قاموس المصطلحات (Vocabulary):
    - لا تقل "السعر هو" -> قل: "سومتها"، "نحسبوهالك بـ"، "راهي دير".
    - لا تقل "مرحباً" -> قل: "واش خويا"، "السلام عليكم"، "أهلا بيك".
    - لا تقل "حسناً" -> قل: "ما يكون لا خاطرك"، "بيان سور"، "ماشي مشكل".
    - لا تقل "للأسف" -> قل: "الله غالب"، "اسمحلنا".
    
    🛑 قواعد الرد (Rules):
    1. **منع الفصحى:** ممنوع استخدام كلمات مثل (سيدي، عزيزي، للأسف، حسناً، جداً). استخدم (خويا، الله يحفظك، بزاف).
    2. **قانون الجملة (Wholesale Only):** إذا طلب الزبون "حبة" أو "قياس واحد"، ارفض بصرامة وأدب.
       - مثال للرفض: "يا خويا اسمحلنا، الورشة تخدم غير السيري (Gros)، ما نقدروش نبيعو بالديتاي."
    3. **التفاعل:** إذا كانت السلعة متوفرة، شجع الزبون: "سلعة شابة الله يبارك"، "موديل مطلوب بزاف".
    4. **الصور:** إذا وجدت رابط صورة، ضعه في آخر الرسالة بكلمة IMAGE:.
    
    📦 السلعة المتوفرة (المخزون):
    {inventory_data}
    """

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_text}
            ],
            temperature=0.3, # تقليل الإبداع للحفاظ على لغة السوق
            max_tokens=200,
        )
        full_response = completion.choices[0].message.content
        
        # --- استخراج الصورة ---
        image_url = None
        reply_text = full_response
        
        if "IMAGE:" in full_response:
            parts = full_response.split("IMAGE:")
            reply_text = parts[0].strip()
            if len(parts) > 1:
                potential_url = parts[1].strip()
                if potential_url.startswith("http"):
                    image_url = potential_url.split()[0]
        
        return reply_text, image_url

    except Exception as e:
        print(f"Groq Error: {e}")
        return "اسمحلنا خويا، كاين ضغط، عاود ابعثلي.", None

def send_fb_message(recipient_id, text):
    """إرسال النص"""
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    requests.post(url, json=payload)

def send_fb_image(recipient_id, image_url):
    """إرسال الصورة كمرفق"""
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
        # طباعة الرابط للتأكد في الـ Logs
        print(f"📸 Trying to send image: {image_url}")
        r = requests.post(url, json=payload)
        if r.status_code != 200:
            print(f"❌ FB Image Error: {r.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

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
                            
                            # 1. جلب الرد والصورة
                            text_reply, img_reply = ask_groq(user_msg)
                            
                            # 2. إرسال النص
                            send_fb_message(sender_id, text_reply)
                            
                            # 3. إرسال الصورة (إذا كاينة)
                            if img_reply:
                                send_fb_image(sender_id, img_reply)
                                
            return "ok", 200
        except Exception:
            traceback.print_exc()
            return "ok", 200

if __name__ == '__main__':
    app.run(port=5000)