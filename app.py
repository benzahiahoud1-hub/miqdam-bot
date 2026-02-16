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
    4. **تنسيق الأرقام:** اكتب الأسعار بدون أصفار زائدة (مث