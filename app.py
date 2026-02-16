import os
import pandas as pd
from flask import Flask, request
import requests
from openai import OpenAI
import io
import traceback
from collections import deque

app = Flask(__name__)

# --- الذاكرة ---
user_memory = {} 
muted_users = set()

# --- المتغيرات ---
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

client = None
if DEEPSEEK_API_KEY:
    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    except Exception as e:
        print(f"❌ Error init DeepSeek: {e}")

# --- برومبت احتياطي (في حال كان الشيت فارغاً) ---
DEFAULT_PROMPT = """
أنت ورشة المقدام. بيع بالجملة فقط. شركة التوصيل أندرسن (69 ولاية، 3 أيام).
الدفع عند الاستلام. تكلم بلهجة جزائرية محترمة.
"""

def format_price(price):
    try:
        return str(int(float(price)))
    except:
        return str(price)

def get_data_from_sheet():
    """جلب المخزون + البرومبت من الشيت"""
    try:
        if not SHEET_URL: return "الرابط مفقود", DEFAULT_PROMPT
        
        response = requests.get(SHEET_URL, timeout=10)
        df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        df.fillna('', inplace=True) 
        
        # 1. استخراج المخزون
        inventory_text = ""
        for _, row in df.iterrows():
            p_name = row.get('Product Name', row.iloc[0])
            p_price = format_price(row.get('Price', row.iloc[1]))
            p_stock = row.get('Stock', row.iloc[2])
            p_img = row.get('Image URL', row.iloc[3])
            
            # نتجاهل الأسطر الفارغة
            if p_name: 
                inventory_text += f"المنتج: {p_name} | السعر: {p_price} دج | الحالة: {p_stock} | الرابط: {p_img}\n"
        
        # 2. استخراج البرومبت (التعليمات)
        # نبحث عن عمود اسمه System_Prompt
        system_prompt = DEFAULT_PROMPT # القيمة الافتراضية
        
        # نحاول العثور على العمود بالاسم، أو نأخذ العمود الخامس إذا لم نجد الاسم
        if 'System_Prompt' in df.columns:
            # نأخذ القيمة من أول سطر فقط
            val = df['System_Prompt'].iloc[0]
            if val and len(str(val)) > 10: # التأكد أنه ليس فارغاً
                system_prompt = str(val)
        
        return inventory_text, system_prompt

    except Exception as e:
        print(f"Sheet Error: {e}")
        return "المخزون قيد التحديث.", DEFAULT_PROMPT

def ask_deepseek(sender_id, user_text):
    if not client: return "الصيانة حالياً.", None, False

    # جلب البيانات (المخزون + التعليمات) في كل رسالة
    inventory_data, dynamic_prompt = get_data_from_sheet()
    
    history = user_memory.get(sender_id, deque(maxlen=8))
    
    # --- دمج التعليمات من الشيت مع المخزون ---
    full_instruction = f"""
    {dynamic_prompt}
    
    📦 قائمة المخزون الحالية:
    {inventory_data}
    """

    messages = [{"role": "system", "content": full_instruction}]
    messages.extend(list(history))
    messages.append({"role": "user", "content": user_text})

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7,
            max_tokens=250
        )
        
        reply = response.choices[0].message.content
        
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})
        user_memory[sender_id] = history

        should_mute = False
        if "[MUTE]" in reply:
            should_mute = True
            reply = reply.replace("[MUTE]", "").strip()
        
        image_url = None
        if "IMAGE:" in reply:
            parts = reply.split("IMAGE:")
            reply = parts[0].strip()
            if "تفضل" not in reply and len(reply) > 20: reply = "تفضل الصور:"
            if len(parts) > 1 and parts[1].strip().startswith("http"):
                image_url = parts[1].strip().split()[0]

        return reply, image_url, should_mute

    except Exception as e:
        print(f"Error: {e}")
        return "لحظة من فضلك...", None, False

def send_fb_message(recipient_id, text):
    if not text: return
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json={"recipient": {"id": recipient_id}, "message": {"text": text}})

def send_fb_image(recipient_id, image_url):
    if not image_url: return
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"attachment": {"type": "image", "payload": {"url": image_url, "is_reusable": True}}}
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

                            if sender_id in muted_users:
                                continue 

                            reply_text, reply_image, mute_request = ask_deepseek(sender_id, user_msg)
                            send_fb_message(sender_id, reply_text)
                            if reply_image: send_fb_image(sender_id, reply_image)
                            
                            if mute_request: muted_users.add(sender_id)
                                
            return "ok", 200
        except:
            traceback.print_exc()
            return "ok", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)