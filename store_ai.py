import streamlit as st
from google import genai
from google.genai import types
import requests

# --- הגדרות ---
# טעינת מפתחות (כולל הגנה למקרה שאין)
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    SHOPIFY_API_KEY = st.secrets["SHOPIFY_API_KEY"]
    SHOPIFY_STORE_URL = st.secrets["SHOPIFY_STORE_URL"]
except:
    st.error("Secrets not found. Please check Streamlit settings.")
    st.stop()

# --- הגדרת עמוד ועיצוב ---
st.set_page_config(page_title="Project 08", page_icon="💎", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* רקע ואנימציות */
    @keyframes gradientBG { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
    html, body, [class*="css"] { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background-color: #000; color: #fff; }
    .stApp { background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); background-size: 400% 400%; animation: gradientBG 15s ease infinite; }
    
    /* עיצוב כרטיסיות מוצר בצד (Sidebar Cards) */
    .product-card { 
        background: rgba(255,255,255,0.05); 
        border: 1px solid rgba(255,255,255,0.1); 
        border-radius: 16px; 
        padding: 15px; 
        margin-bottom: 12px; 
        cursor: pointer; 
        backdrop-filter: blur(10px); 
        transition: all 0.3s ease; 
    }
    .product-card:hover { 
        transform: translateY(-5px); 
        border-color: #00d2ff; 
        background: rgba(255,255,255,0.15); 
        box-shadow: 0 5px 15px rgba(0,210,255,0.3); 
    }
    .card-title { font-weight: 600; font-size: 15px; color: #fff; margin-bottom: 4px; }
    .card-price { color: #00d2ff; font-size: 14px; font-weight: bold; }
    .card-qty { float: right; color: #aaa; font-size: 12px; }
    
    /* עיצוב בועות צ'אט */
    div[data-testid="stChatMessage"] { background: transparent; border: none; padding: 0; }
    div[data-testid="stChatMessage"]:nth-child(odd) div[data-testid="stMarkdownContainer"] { background: rgba(255,255,255,0.05); border-radius: 20px 20px 20px 5px; padding: 12px 18px; color: #eee; border: 1px solid rgba(255,255,255,0.05); }
    div[data-testid="stChatMessage"]:nth-child(even) div[data-testid="stMarkdownContainer"] { background: linear-gradient(135deg, #00d2ff, #3a7bd5); border-radius: 20px 20px 5px 20px; padding: 12px 18px; color: #fff; text-align: right; box-shadow: 0 4px 15px rgba(0,210,255,0.2); }
    
    /* תמונות וקלט */
    .stMarkdown img { border-radius: 12px; margin-top: 10px; max-width: 250px; border: 1px solid rgba(255,255,255,0.1); }
    .stTextInput input { background: rgba(0,0,0,0.3) !important; border: 1px solid rgba(255,255,255,0.2) !important; color: white !important; border-radius: 25px; padding: 10px 15px; }
    #MainMenu, footer, header {visibility: hidden;}
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
            raw_data = []
            for p in products:
                try:
                    title = p['title']
                    handle = p['handle']
                    variant = p['variants'][0]
                    price = variant['price']
                    qty = variant['inventory_quantity']
                    img = p['images'][0]['src'] if p.get('images') else ""
                    link = f"https://{SHOPIFY_STORE_URL}/products/{handle}"
                    raw_data.append({"title": title, "price": price, "qty": qty, "link": link, "img": img})
                except: continue
            return raw_data
        return []
    except:
        return []

def get_system_instruction(inventory):
    inv_text = "\n".join([f"- {p['title']} (Price: {p['price']}, Link: {p['link']}, Image: {p['img']})" for p in inventory])
    return f"""
    You are the AI assistant for 'Project 08'.
    PROTOCOL:
    1. Language: English default. Hebrew ONLY if user writes in Hebrew.
    2. Style: Short, cool, sales-oriented.
    3. Images: You MUST display images like this: [![Product](ImageURL)](ProductLink)
    4. INVENTORY DATA:
    {inv_text}
    """

# --- אתחול הלקוח (עם המודל שעובד) ---
client = genai.Client(api_key=GOOGLE_API_KEY)
# משתמשים במודל הנסיוני שעבד בבדיקה שלך
WORKING_MODEL = "gemini-2.0-flash-exp" 

# --- ממשק ---

# ==== החלק שהוספתי: סרגל צד עם מוצרים ====
with st.sidebar:
    st.markdown("### 💎 Collection")
    
    # טעינת מוצרים
    products = get_inventory()
    
    if products:
        for p in products:
            # כרטיסיית מוצר לחיצה
            st.markdown(f"""
            <a href="{p['link']}" target="_blank" style="text-decoration:none;">
                <div class="product-card">
                    <div class="card-title">{p['title']}</div>
                    <div class="card-price">₪{p['price']} 
                        <span class="card-qty">● Stock: {p['qty']}</span>
                    </div>
                </div>
            </a>
            """, unsafe_allow_html=True)
    else:
        st.info("Loading store items...")
# =========================================

st.markdown("<h1 style='text-align: center; text-shadow: 0 0 20px rgba(0,210,255,0.6);'>PROJECT 08</h1>", unsafe_allow_html=True)

# אתחול צ'אט
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Welcome to Project 08. / ברוכים הבאים"}]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=True)

# קלט משתמש
if prompt := st.chat_input("Type here..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        # הכנת ההיסטוריה
        history = [{"role": "user" if m["role"]=="user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.messages[:-1]]
        
        # שליחה למודל
        chat = client.chats.create(
            model=WORKING_MODEL,
            history=history,
            config=types.GenerateContentConfig(
                system_instruction=get_system_instruction(products),
                temperature=0.7
            )
        )
        
        with st.spinner("Processing..."):
            response = chat.send_message(prompt)
        
        st.session_state.messages.append({"role": "assistant", "content": response.text})
        with st.chat_message("assistant"):
            st.markdown(response.text, unsafe_allow_html=True)
            
    except Exception as e:
        st.error("System Refreshing... Please try again.")
