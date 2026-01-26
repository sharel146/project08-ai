import streamlit as st
from google import genai
from google.genai import types
import requests

# --- הגדרת עמוד (חייב להיות ראשון) ---
st.set_page_config(page_title="Project 08", page_icon="💎", layout="wide", initial_sidebar_state="collapsed")

# --- משיכת מפתחות מהכספת (Secrets) ---
# אם אנחנו מריצים מקומית ואין כספת, נשתמש בברירת מחדל (למקרה שתבדוק במחשב שלך)
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    SHOPIFY_API_KEY = st.secrets["SHOPIFY_API_KEY"]
    SHOPIFY_STORE_URL = st.secrets["SHOPIFY_STORE_URL"]
except:
    # גיבוי למקרה שאתה מריץ במחשב בלי קובץ secrets.toml
    GOOGLE_API_KEY = "AIzaSyDgyLTrbLQ6CdsV0ol8OyFkWP98IxIUf7c"
    SHOPIFY_API_KEY = "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"
    SHOPIFY_STORE_URL = "project08-2.myshopify.com"

# --- אתחול הלקוח ---
try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"Config Error: {e}")
    st.stop()

# --- רשימת מודלים ---
TARGET_MODELS = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro"]

# --- עיצוב ---
st.markdown("""
<style>
    html, body, [class*="css"] { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background-color: #000; color: #fff; }
    .stApp { background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); background-size: 400% 400%; }
    .product-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 15px; margin-bottom: 12px; cursor: pointer; backdrop-filter: blur(10px); transition: 0.2s; }
    .product-card:hover { transform: scale(1.02); border-color: #0A84FF; background: rgba(255,255,255,0.1); }
    .card-title { font-weight: 600; font-size: 15px; color: #fff; margin-bottom: 4px; }
    .card-price { color: #00d2ff; font-size: 14px; }
    .card-stock { float: right; color: #30D158; font-size: 12px; }
    div[data-testid="stChatMessage"] { background: transparent; border: none; padding: 0; }
    div[data-testid="stChatMessage"]:nth-child(odd) div[data-testid="stMarkdownContainer"] { background: rgba(255,255,255,0.1); border-radius: 18px; padding: 12px 16px; color: #fff; backdrop-filter: blur(5px); }
    div[data-testid="stChatMessage"]:nth-child(even) div[data-testid="stMarkdownContainer"] { background: #007AFF; border-radius: 18px; padding: 12px 16px; color: #fff; text-align: right; }
    .stMarkdown img { border-radius: 12px; margin-top: 10px; max-width: 250px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
    #MainMenu, footer, header {visibility: hidden;}
    .stTextInput input { background: rgba(0,0,0,0.3) !important; border: 1px solid rgba(255,255,255,0.2) !important; color: white !important; border-radius: 20px; }
</style>
""", unsafe_allow_html=True)

# --- לוגיקה ---
@st.cache_resource
def get_inventory():
    try:
        url = f"https://{SHOPIFY_STORE_URL}/admin/api/2024-01/products.json?status=active&limit=50"
        headers = {"X-Shopify-Access-Token": SHOPIFY_API_KEY, "Content-Type": "application/json"}
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            products = response.json().get('products', [])
            text_data = ""
            raw_data = []
            for p in products:
                title = p['title']
                handle = p['handle']
                variant = p['variants'][0]
                price = variant['price']
                qty = variant['inventory_quantity']
                img = p['images'][0]['src'] if p.get('images') else "NO_IMAGE"
                link = f"https://{SHOPIFY_STORE_URL}/products/{handle}"
                text_data += f"Product: {title} | Price: {price} | Link: {link} | Image: {img}\n"
                raw_data.append({"title": title, "price": price, "qty": qty, "link": link})
            return text_data, raw_data
        return "", []
    except:
        return "", []

def convert_history(messages):
    history = []
    for msg in messages:
        if msg["role"] in ["user", "assistant"]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [{"text": str(msg["content"])}]})
    return history

def get_system_instruction():
    inventory_text, _ = get_inventory()
    return f"""
    You are Project 08 AI.
    PROTOCOL:
    1. Language: English default. Hebrew ONLY if user speaks Hebrew.
    2. Visuals: Clickable links -> [![Alt](ImageURL)](ProductLink)
    3. DATA: {inventory_text}
    """

def find_working_model():
    for model_name in TARGET_MODELS:
        try:
            client.models.generate_content(model=model_name, contents="ping", config=types.GenerateContentConfig(max_output_tokens=1))
            return model_name
        except: continue
    return None

# --- ממשק ---
with st.sidebar:
    st.markdown("### 💎 Collection")
    _, products = get_inventory()
    if products:
        for p in products:
            st.markdown(f"""
            <a href="{p['link']}" target="_blank" style="text-decoration:none;">
                <div class="product-card">
                    <div class="card-title">{p['title']}</div>
                    <div class="card-price">₪{p['price']} <span class="card-stock">● {p['qty']}</span></div>
                </div>
            </a>""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align: center;'>PROJECT 08</h1>", unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Welcome to Project 08."}]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=True)

if prompt := st.chat_input("Type here..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        new_history = convert_history(st.session_state.messages[:-1])
        
        if "valid_model" not in st.session_state:
            found_model = find_working_model()
            if found_model: st.session_state.valid_model = found_model
            else: 
                st.error("System Busy.")
                st.stop()
        
        chat = client.chats.create(model=st.session_state.valid_model, config=types.GenerateContentConfig(system_instruction=get_system_instruction()), history=new_history)
        
        with st.spinner("Processing..."):
            response = chat.send_message(prompt)
        
        st.session_state.messages.append({"role": "assistant", "content": response.text})
        with st.chat_message("assistant"):
            st.markdown(response.text, unsafe_allow_html=True)
    except Exception as e:
        if "valid_model" in st.session_state: del st.session_state.valid_model
        st.rerun()