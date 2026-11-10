import streamlit as st
import sqlite3
import hashlib
import uuid
import base64
import json
import requests
from datetime import datetime, timezone
from PIL import Image
from io import BytesIO
from openai import OpenAI

# --- OWNER & PAYMENT CONFIGURATION ---
ADMIN_EMAIL = "bulumadavid20@gmail.com"  # Change to your login email for FREE VIP Ultimate access
STRIPE_PAYMENT_LINK = "https://stripe.com"  # Replace with your Stripe/PayPal link
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
FINNHUB_API_KEY = st.secrets.get("FINNHUB_API_KEY", "YOUR_FINNHUB_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# --- PAGE & DARK THEME STYLING ---
st.set_page_config(page_title="AI Trade Lens", page_icon="⚡", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #0B0C10; color: #FFFFFF; }
    .stButton>button { border-radius: 10px; font-weight: bold; }
    div[data-testid="stMetricValue"] { color: #A855F7; }
    .card { background-color: #161822; padding: 16px; border-radius: 12px; border: 1px solid #2A2D3D; margin-bottom: 12px; }
    </style>
""", unsafe_allow_html=True)

# --- DATABASE SETUP (SQLite for Users & Referrals) ---
conn = sqlite3.connect("users.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY,
        password TEXT,
        plan TEXT,
        ref_code TEXT,
        referred_by TEXT,
        scans_today INTEGER
    )
""")
conn.commit()

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def get_user(email):
    c.execute("SELECT * FROM users WHERE email=?", (email.lower().strip(),))
    return c.fetchone()

def create_user(email, pw, referred_by=""):
    email = email.lower().strip()
    plan = "ULTIMATE" if email == ADMIN_EMAIL.lower().strip() else "FREE"
    ref_code = "REF" + uuid.uuid4().hex[:6].upper()
    try:
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)", (email, hash_pw(pw), plan, ref_code, referred_by, 0))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

# --- REFERRAL URL CAPTURE (?ref=CODE) ---
query_params = st.query_params
incoming_ref = query_params.get("ref", "")

if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "signals_history" not in st.session_state:
    st.session_state.signals_history = []

# --- AUTHENTICATION SCREEN (Matches your screenshot link style) ---
if not st.session_state.user_email:
    st.title("⚡ AI Trade Lens")
    st.caption("Institutional Chart Vision, NFP/CPI NewsIQ & Auto-Trading")
    
    auth_tab1, auth_tab2 = st.tabs(["🔑 Log In", "📝 Create Free Account"])
    
    with auth_tab1:
        login_email = st.text_input("Email Address", key="l_email")
        login_pw = st.text_input("Password", type="password", key="l_pw")
        if st.button("Log In", type="primary", use_container_width=True):
            user = get_user(login_email)
            if user and user[1] == hash_pw(login_pw):
                st.session_state.user_email = user[0]
                st.rerun()
            else:
                st.error("Invalid email or password.")
                
    with auth_tab2:
        reg_email = st.text_input("Email Address", key="r_email")
        reg_pw = st.text_input("Create Password", type="password", key="r_pw")
        ref_input = st.text_input("Referral Code (Optional)", value=incoming_ref)
        if st.button("Sign Up Free", type="primary", use_container_width=True):
            if reg_email and reg_pw:
                if create_user(reg_email, reg_pw, ref_input):
                    st.success("Account created! Switch to 'Log In' tab.")
                else:
                    st.error("Email already registered.")
            else:
                st.warning("Please enter both email and password.")
    st.stop()

# --- LOAD LOGGED-IN USER ---
user_data = get_user(st.session_state.user_email)
user_email, _, user_plan, user_ref_code, _, scans_today = user_data
is_vip = (user_plan == "ULTIMATE") or (user_email == ADMIN_EMAIL.lower().strip())

# --- HELPER FUNCTIONS ---
def fetch_macro_news():
    try:
        url = f"https://finnhub.io{FINNHUB_API_KEY}"
        res = requests.get(url, timeout=6).json()
        events = res.get("economicCalendar", [])
        usd_high = [e for e in events if e.get("country") == "US" and e.get("impact") == "high"]
        return usd_high[:6]
    except Exception:
        return []

def encode_img(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def analyze_chart(b64_image, custom_rules, multi_tf):
    prompt = f"""
    You are an institutional quantitative trading AI. Analyze the chart screenshot.
    Multi-Timeframe Mode: {multi_tf}
    Strategy Rules: {custom_rules}
    Return ONLY valid JSON with keys: asset, timeframe, market_bias, signal, confidence_percent, entry_price, stop_loss, take_profit_1, take_profit_2, risk_reward, reasoning.
    """
    res = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": [
                {"type": "text", "text": "Analyze this chart and provide exact entry, SL, TP, and confidence."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}}
            ]}
        ],
        temperature=0.1
    )
    return json.loads(res.choices[0].message.content)

# --- TOP BAR ---
col_top1, col_top2 = st.columns([3, 1])
with col_top1:
    badge = "👑 OWNER / ULTIMATE" if is_vip else "🆓 FREE PLAN"
    st.markdown(f"**{user_email}** • `{badge}`")
with col_top2:
    if st.button("Logout"):
        st.session_state.user_email = None
        st.rerun()

# --- NAVIGATION TABS ---
tabs = ["🏠 Overview", "⬆️ Upload Chart", "📰 NewsIQ (NFP/CPI)", "💬 AI Assistant", "⚡ Auto & MT5", "💎 Upgrade / Refer"]
if user_email == ADMIN_EMAIL.lower().strip():
    tabs.append("🛠️ Admin")

selected_tabs = st.tabs(tabs)

# --- TAB 1: OVERVIEW & MARKET PULSE ---
with selected_tabs[0]:
    st.subheader("Dashboard Overview")
    c1, c2, c3 = st.columns(3)
    c1.metric("Analyses Run", len(st.session_state.signals_history))
    c2.metric("Account Tier", "ULTIMATE" if is_vip else "FREE")
    c3.metric("News Protection", "ACTIVE" if is_vip else "LOCKED")
    
    st.subheader("Live Market Pulse")
    p1, p2, p3 = st.columns(3)
    p1.metric("XAUUSD (Gold)", "Live Feed", "+0.45%")
    p2.metric("EURUSD", "Live Feed", "+0.12%")
    p3.metric("BTCUSD", "Live Feed", "+1.85%")
    
    st.subheader("Recent Pulse Signals")
    if not st.session_state.signals_history:
        st.info("No signals generated yet. Tap 'Upload Chart' to scan your first chart!")
    for s in reversed(st.session_state.signals_history[-5:]):
        with st.container(border=True):
            st.write(f"**{s.get('asset', 'Chart')}** ({s.get('timeframe', 'M5')}) — **{s.get('signal')}** ({s.get('confidence_percent')}% Confidence)")
            st.caption(f"Entry: `{s.get('entry_price')}` | SL: `{s.get('stop_loss')}` | TP1: `{s.get('take_profit_1')}` | R:R: {s.get('risk_reward')}")

# --- TAB 2: UPLOAD CHART SCANNER ---
with selected_tabs[1]:
    st.subheader("Upload Your Chart")
    st.caption("Upload a screenshot from TradingView or MT5 to get Entry, SL, TP & Confidence %.")
    
    multi_tf = st.toggle("Multi-Timeframe Analysis Mode (VIP)", value=False, disabled=not is_vip)
    custom_strategy = st.text_input("Custom Strategy Focus (Optional)", value="Price action, liquidity sweeps, support/resistance")
    uploaded_img = st.file_uploader("Upload Chart Image (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"])
    
    if uploaded_img:
        img = Image.open(uploaded_img)
        st.image(img, caption="Uploaded Chart", use_container_width=True)
        
        if st.button("🔍 Analyze Chart Now", type="primary", use_container_width=True):
            if not is_vip and scans_today >= 2:
                st.error("Free Plan limit reached (2 scans/day). Go to 'Upgrade' tab for unlimited scans!")
            else:
                with st.spinner("AI Vision scanning candlestick structure..."):
                    b64 = encode_img(img)
                    result = analyze_chart(b64, custom_strategy, multi_tf)
                    st.session_state.signals_history.append(result)
                    c.execute("UPDATE users SET scans_today = scans_today + 1 WHERE email=?", (user_email,))
                    conn.commit()
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Signal", result.get("signal", "WAIT"))
                    m2.metric("Confidence", f"{result.get('confidence_percent', 0)}%")
                    m3.metric("Risk : Reward", result.get("risk_reward", "N/A"))
                    
                    st.success(f"🎯 **Entry:** `{result.get('entry_price')}` | 🛑 **SL:** `{result.get('stop_loss')}` | ✅ **TP1:** `{result.get('take_profit_1')}` | ✅ **TP2:** `{result.get('take_profit_2')}`")
                    for reason in result.get("reasoning", []):
                        st.write(f"• {reason}")

# --- TAB 3: NEWSIQ (NFP / CPI CALENDAR) ---
with selected_tabs[2]:
    st.subheader("📰 NewsIQ — High-Impact NFP & CPI Events")
    if not is_vip:
        st.warning("🔒 NewsIQ Live NFP/CPI Countdown & AI Impact Analyzer is an Ultimate Plan feature.")
        st.link_button("Upgrade to Ultimate Plan", STRIPE_PAYMENT_LINK, type="primary")
    else:
        events = fetch_macro_news()
        if not events:
            st.success("✅ No imminent high-impact USD news (NFP/CPI/FOMC) detected right now. Safe to scalp!")
        else:
            for ev in events:
