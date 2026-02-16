import os
import pandas as pd
from flask import Flask, request
import requests
from openai import OpenAI # نستخدم مكتبة OpenAI للاتصال بـ DeepSeek
import io
import traceback

app = Flask(__name__)

# --- الصفحة الرئيسية ---
@app.route('/')
def home():
    return "✅ Miqdam Bot (DeepSeek Edition) is Running!", 200

# --- المتغيرات ---
# تأكد من تسمية المتغير في Render بـ DEEPSEEK_API_KEY
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# --- إعداد DeepSeek ---
client = None
if DEEPSEEK_API_KEY:
    try:
        # DeepSeek يستخدم نفس بروتوكول OpenAI
        client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
        print("✅ DeepSeek Connected Successfully")
    except Exception as e:
        print(f"❌ Error init DeepSeek: {e}")
else:
    print("⚠️ Warning: DEEPSEEK_API_KEY is missing")

def get_inventory():
    """جلب المخزون"""
    try:
        if not SHEET_URL:
            return "رابط الشيت مفقود."

        response = requests.get(SHEET_URL, timeout=10)
        response.raise_for_status()

        df = pd.read_csv(io.StringIO(response.content.decode('utf-8')))
        df.fillna('', inplace=True)

        text = ""
        for _, row in df.iterrows():
            p_name = row.get('Product Name', row.iloc[0])
            p_price = row.get('Price', row.iloc[1])
            p_stock = row.get('Stock', row.iloc[2])
            p_img = row.get('Image URL', row.iloc[3])

            text += f"المنتج: {p_name} | السعر: {p_price} | الحالة: {p_stock} | الرابط: {p_img}\n"
        return text
    except Exception as e:
        print(f"⚠️ Error reading sheet: {e}")
        return "المخزون غير متوفر حالياً."

def ask_deepseek(user_text):
    if not client:
        return "السيرفر في حالة صيانة، دقيقة ونرجعو.", None

    inventory_data = get_inventory()

    # --- 🔴 برومبت DeepSeek المحترم (Polite V3) 🔴 ---
    system_instruction = f"""
    أنت 'أمين'، مسؤول المبيعات في 'ورشة المقدام'.

    🎯 المهمة:
    الرد على الزبائن بلهجة جزائرية (Algiers Dialect) غاية في الأدب والاحترام.

    📜 القواعد الصارمة:
    1. **الاحترام  :** عامِل الزبون بأدب. استخدم عبارات: "الله يحفظك"، "ربي يعيشك"، "مرحبا بيك".
    2. **التواضع:** لا تكن جافاً. كن بشوشاً ولطيفاً جداً (Very friendly and humble).
    3. **سياسة البيع:** نحن نبيع **بالجملة فقط**.
       - إذا طلب "ديتاي" (تجزئة)، اعتذر منه بألطف طريقة ممكنة.
       - مثال للرفض: "يا خويا العزيز، والله غير اسمحلنا، الورشة تخدم غير الجملة، ربي يبارك فيك."
    4. **الصور:** إذا وجدت رابطاً للمنتج، ضعه في النهاية بعد كلمة IMAGE:.

    📦 القائمة:
    {inventory_data}
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat", # هذا هو الموديل الذكي والسريع
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_text}
            ],
            temperature=1.1, # DeepSeek يحب حرارة أعلى قليلاً للإبداع
            max_tokens=250,
            stream=False
        )

        full_response = response.choices[0].message.content

        # استخراج الصورة
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
        print(f"❌ DeepSeek Error: {e}")
        return "اسمحلنا خويا، كاين ضغط، عاود ابعثلي.", None

def send_fb_message(recipient_id, text):
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
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"⚠️ FB Image Error: {e}")

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

                            reply_text, reply_image = ask_deepseek(user_msg)
                            send_fb_message(sender_id, reply_text)
                            if reply_image:
                                send_fb_image(sender_id, reply_image)
            return "ok", 200
        except Exception:
            traceback.print_exc()
            return "ok", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
