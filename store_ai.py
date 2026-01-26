import streamlit as st
from google import genai
from google.genai import types
import requests

# --- הגדרת עמוד ---
st.set_page_config(page_title="Project 08 - Debug", page_icon="🔧", layout="wide")

st.markdown("<h1 style='text-align: center; color: red;'>MODE: DEBUG & REPAIR</h1>", unsafe_allow_html=True)

# --- שליפת מפתחות ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    SHOPIFY_API_KEY = st.secrets["SHOPIFY_API_KEY"]
    SHOPIFY_STORE_URL = st.secrets["SHOPIFY_STORE_URL"]
    st.success("✅ Secrets loaded successfully.")
except Exception as e:
    st.error(f"❌ Secret Error: {e}")
    st.stop()

# --- בדיקת חיבור לגוגל (החלק הקריטי) ---
st.info("🔄 Attempting to connect to Google AI...")

try:
    # 1. יצירת לקוח
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    # 2. ניסיון פינג ישיר למודל הכי בסיסי
    st.write("Pinging 'gemini-1.5-flash'...")
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents="Ping",
        config=types.GenerateContentConfig(max_output_tokens=5)
    )
    
    st.success(f"✅ Connection Successful! AI Replied: {response.text}")
    active_model = "gemini-1.5-flash"

except Exception as e:
    st.error(f"❌ CRITICAL AI ERROR: {e}")
    st.warning("Trying backup model 'gemini-2.0-flash-exp'...")
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents="Ping"
        )
        st.success(f"✅ Backup Model Works! AI Replied: {response.text}")
        active_model = "gemini-2.0-flash-exp"
    except Exception as e2:
        st.error(f"❌ Backup failed too: {e2}")
        st.stop()

# --- אם הגענו לפה - הבוט עובד! ---
# --- מכאן מתחיל הקוד הרגיל של החנות ---

st.markdown("---")
st.markdown("### 💎 Store Interface Loading...")

@st.cache_resource
def get_inventory():
    try:
        url = f"https://{SHOPIFY_STORE_URL}/admin/api/2024-01/products.json?status=active&limit=50"
        headers = {"X-Shopify-Access-Token": SHOPIFY_API_KEY, "Content-Type": "application/json"}
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            return response.json().get('products', [])
        return []
    except Exception as e:
        st.error(f"Shopify Error: {e}")
        return []

# ממשק צ'אט
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "System operational. How can I help?"}]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Type here..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        # המרה לפורמט החדש
        history = [{"role": "user" if m["role"]=="user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.messages[:-1]]
        
        chat = client.chats.create(
            model=active_model,
            history=history,
            config=types.GenerateContentConfig(system_instruction="You are a helpful store assistant.")
        )
        response = chat.send_message(prompt)
        
        st.session_state.messages.append({"role": "assistant", "content": response.text})
        with st.chat_message("assistant"):
            st.markdown(response.text)
            
    except Exception as e:
        st.error(f"Chat Error: {e}")
