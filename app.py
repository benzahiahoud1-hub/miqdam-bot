import os
import pandas as pd
from flask import Flask, request
import requests
from openai import OpenAI
import io
import traceback
from collections import deque # مكتبة لتنظيم الذاكرة

app = Flask(__name__)

# --- 🧠 الذاكرة ونظام الصمت ---
# تخزين آخر 8 رسائل لكل زبون (للتركيز على المنتج)
user_memory = {} 
# قائمة الزبائن الذين يجب أن يتوقف البوت عن الرد عليهم (ليتدخل البشر)
muted_users = set()

@app.route('/')
def home():
    return "✅ Miqdam Smart Bot (Anderson Edition) is Live!", 200

# --- المتغيرات ---
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# --- إعداد DeepSeek ---
client = None
if DEEPSEEK_API_KEY:
    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    except Exception as e:
        print(f"❌ Error init DeepSeek: {e}")

def format_price(price):
    """إزالة الفاصلة العشرية من السعر"""
    try:
        return str(int(float(price)))
    except:
        return str(price)

def get_inventory():
    """جلب المخزون وتنسيقه"""
    try:
        if not SHEET_URL: return "الرابط مفقود"
        response = requests.get(SHEET_URL, timeout=10)
        df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        df.fillna('', inplace=True) 
        
        text = ""
        for _, row in df.iterrows():
            p_name = row.get('Product Name', row.iloc[0])
            p_price = format_price(row.get('Price', row.iloc[1]))
            p_stock = row.get('Stock', row.iloc[2])
            p_img = row.get('Image URL', row.iloc[3])
            
            text += f"المنتج: {p_name} | السعر: {p_price} دج | الحالة: {p_stock} | الرابط: {p_img}\n"
        return text
    except:
        return "المخزون قيد التحديث."

def ask_deepseek(sender_id, user_text):
    if not client: return "الصيانة حالياً.", None, False

    inventory_data = get_inventory()
    
    # استرجاع ذاكرة هذا المستخدم
    history = user_memory.get(sender_id, deque(maxlen=8))
    
    # --- 🔴 العقل المدبر (The Brain) 🔴 ---
    system_instruction = f"""
    أنت هو "ورشة المقدام" (كيان تجاري ولست شخصاً).
    
    📦 معلومات الشحن والدفع (مهمة جداً):
    - شركة التوصيل: "أندرسن" (Anderson).
    - التغطية: موجودة في **69 ولاية**.
    - مدة التوصيل: **حوالي 3 أيام**.
    - الدفع: **عند الاستلام** (Main à main).
    
    🛑 القواعد الصارمة (System Rules):
    1. **الهوية:** عرّف بنفسك "معك ورشة المقدام". لا تقل "أنا أمين".
    2. **سياق الحديث:** انتبه للرسائل السابقة. اعرف المنتج الذي يتكلم عنه الزبون ولا تذكر منتجات أخرى عشوائياً.
    3. **قاعدة الجملة:** اذكر "البيع بالجملة فقط" (Gros) **مرة واحدة فقط** في بداية التعارف. لا تكررها كل مرة.
    4. **تنسيق الأرقام:** اكتب الأسعار بدون أصفار زائدة (مثلاً 5000 وليس 5000.0).
    5. **الصور:** إذا طلب الزبون صوراً، أرسل الرابط فقط مع كلمة "تفضل". لا تكثر الكلام.
    
    🚨 أوامر الصمت والتدخل البشري (Triggers):
    في الحالات التالية، يجب عليك إنهاء الرد بكلمة **[MUTE]**:
    
    أ- **سعر التوصيل:** إذا سأل عن "سعر التوصيل" أو "شحال التوصيل":
       - قل فقط: "دقيقة أخي، سيتم الرد عليك بخصوص التوصيل..."
       - ثم ضع [MUTE]. (لتتوقف عن الكلام ويتدخل المالك).
       
    ب- **إتمام الطلب:** إذا قدم الزبون معلوماته (الاسم، العنوان، الهاتف):
       - قل: "تم تسجيل الطلب. يوصلك خلال 3 أيام عبر شركة أندرسن (69 ولاية). الدفع عند الاستلام. بصحتك."
       - ثم ضع [MUTE]. (لتتوقف عن الكلام).

    📦 المخزون:
    {inventory_data}
    """

    # بناء المحادثة
    messages = [{"role": "system", "content": system_instruction}]
    messages.extend(list(history)) # إضافة الماضي
    messages.append({"role": "user", "content": user_text})

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7, # قللنا الحرارة ليكون أكثر دقة
            max_tokens=200
        )
        
        reply = response.choices[0].message.content
        
        # تحديث الذاكرة
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})
        user_memory[sender_id] = history

        # --- معالجة الأوامر الخاصة ---
        
        # 1. هل طلب البوت الصمت؟ ([MUTE])
        should_mute = False
        if "[MUTE]" in reply:
            should_mute = True
            reply = reply.replace("[MUTE]", "").strip() # حذف الكلمة السرية من الرسالة
        
        # 2. استخراج الصورة
        image_url = None
        if "IMAGE:" in reply:
            parts = reply.split("IMAGE:")
            reply = parts[0].strip() # النص
            # إذا كان النص طويلاً وطلب صورة، نختصره
            if "تفضل" not in reply and len(reply) > 20:
                 reply = "تفضل الصور:"
            
            if len(parts) > 1:
                potential_url = parts[1].strip()
                if potential_url.startswith("http"):
                    image_url = potential_url.split()[0]

        return reply, image_url, should_mute

    except Exception as e:
        print(f"Error: {e}")
        return "لحظة من فضلك...", None, False

def send_fb_message(recipient_id, text):
    if not text: return # لا ترسل رسائل فارغة
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
                            sender_id = event['sender']['id']
                            user_msg = event['message']['text']
                            
                            if event['message'].get('is_echo'): continue

                            # 🛑 التحقق: هل هذا المستخدم في قائمة الصمت؟
                            if sender_id in muted_users:
                                print(f"User {sender_id} is muted. Waiting for human.")
                                continue # تجاهل الرسالة (لا ترد عليه)

                            # الحصول على الرد
                            reply_text, reply_image, mute_request = ask_deepseek(sender_id, user_msg)
                            
                            # تنفيذ الردود
                            send_fb_message(sender_id, reply_text)
                            if reply_image:
                                send_fb_image(sender_id, reply_image)
                            
                            # 🛑 تفعيل الصمت إذا طلبه البوت
                            if mute_request:
                                muted_users.add(sender_id)
                                print(f"🔇 Muting user {sender_id} per AI request.")
                                
            return "ok", 200
        except:
            traceback.print_exc()
            return "ok", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

    # تنفيذ الردود