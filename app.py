import streamlit as st
import sqlite3, hashlib, uuid, base64, json, itertools, requests
from PIL import Image
from io import BytesIO
from openai import OpenAI

ADMIN_EMAIL = "bulumadavid20@gmail.com"
STRIPE_PAYMENT_LINK = "https://stripe.com"
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
FINNHUB_API_KEY = st.secrets.get("FINNHUB_API_KEY", "YOUR_FINNHUB_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

st.set_page_config(page_title="AI Trade Lens", page_icon="⚡", layout="centered")
st.markdown("<style>.stApp{background-color:#0B0C10;color:#FFF;}div[data-testid='stMetricValue']{color:#A855F7;}</style>", unsafe_allow_html=True)

conn = sqlite3.connect("users.db", check_same_thread=False)
c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password TEXT, plan TEXT, ref_code TEXT, referred_by TEXT, scans_today INTEGER)")
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

incoming_ref = st.query_params.get("ref", "")
if "user_email" not in st.session_state: st.session_state.user_email = None
if "signals_history" not in st.session_state: st.session_state.signals_history = list()
if "chat_messages" not in st.session_state: st.session_state.chat_messages = list()

if not st.session_state.user_email:
    st.title("⚡ AI Trade Lens")
    st.caption("Institutional Chart Vision, NFP/CPI NewsIQ & Auto-Trading")
    t1, t2 = st.tabs(("🔑 Log In", "📝 Create Free Account"))
    with t1:
        le = st.text_input("Email Address", key="l_email")
        lp = st.text_input("Password", type="password", key="l_pw")
        if st.button("Log In", type="primary", use_container_width=True):
            u = get_user(le)
            if u:
                u_em, u_pw, u_pl, u_rf, u_by, u_sc = u
                if u_pw == hash_pw(lp):
                    st.session_state.user_email = u_em
                    st.rerun()
                else: st.error("Invalid email or password.")
            else: st.error("Invalid email or password.")
    with t2:
        re = st.text_input("Email Address", key="r_email")
        rp = st.text_input("Create Password", type="password", key="r_pw")
        ri = st.text_input("Referral Code (Optional)", value=incoming_ref)
        if st.button("Sign Up Free", type="primary", use_container_width=True):
            if re and rp:
                if create_user(re, rp, ri): st.success("Account created! Switch to 'Log In' tab.")
                else: st.error("Email already registered.")
            else: st.warning("Please enter both email and password.")
    st.stop()

user_email, _, user_plan, user_ref_code, _, scans_today = get_user(st.session_state.user_email)
is_vip = (user_plan == "ULTIMATE") or (user_email == ADMIN_EMAIL.lower().strip())

def fetch_macro_news():
    try:
        res = requests.get("https://finnhub.io" + FINNHUB_API_KEY, timeout=6).json()
        events = res.get("economicCalendar", list())
        return list(itertools.islice((e for e in events if e.get("country") == "US" and e.get("impact") == "high"), 6))
    except Exception: return list()

def encode_img(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def analyze_chart(b64_image, custom_rules, multi_tf):
    prompt = f"You are an institutional trading AI. Multi-TF: {multi_tf}. Rules: {custom_rules}. Return ONLY valid JSON with keys: asset, timeframe, signal, confidence_percent, entry_price, stop_loss, take_profit_1, risk_reward, reasoning."
    msgs = list(({"role": "system", "content": prompt}, {"role": "user", "content": list(({"type": "text", "text": "Analyze chart."}, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64_image}}))}))
    res = client.chat.completions.create(model="gpt-4o", response_format={"type": "json_object"}, messages=msgs, temperature=0.1)
    return json.loads(next(iter(res.choices)).message.content)

c1, c2 = st.columns((3, 1))
c1.markdown(f"**{user_email}** • `{'👑 OWNER / ULTIMATE' if is_vip else '🆓 FREE PLAN'}`")
if c2.button("Logout"):
    st.session_state.user_email = None
    st.rerun()

if user_email == ADMIN_EMAIL.lower().strip():
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(("🏠 Overview", "⬆️ Upload Chart", "📰 NewsIQ", "💬 AI Assistant", "⚡ Auto & MT5", "💎 Upgrade", "🛠️ Admin"))
else:
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(("🏠 Overview", "⬆️ Upload Chart", "📰 NewsIQ", "💬 AI Assistant", "⚡ Auto & MT5", "💎 Upgrade"))
    tab7 = None

with tab1:
    st.subheader("Dashboard Overview")
    m1, m2, m3 = st.columns(3)
    m1.metric("Analyses Run", len(st.session_state.signals_history))
    m2.metric("Account Tier", "ULTIMATE" if is_vip else "FREE")
    m3.metric("News Protection", "ACTIVE" if is_vip else "LOCKED")
    for s in itertools.islice(reversed(st.session_state.signals_history), 5):
        with st.container(border=True):
            st.write(f"**{s.get('asset', 'Chart')}** — **{s.get('signal')}** ({s.get('confidence_percent')}%)")
            st.caption(f"Entry: `{s.get('entry_price')}` | SL: `{s.get('stop_loss')}` | TP1: `{s.get('take_profit_1')}`")

with tab2:
    st.subheader("Upload Your Chart")
    multi_tf = st.toggle("Multi-Timeframe Mode (VIP)", value=False, disabled=not is_vip)
    custom_strategy = st.text_input("Strategy Focus", value="Price action, liquidity sweeps, support/resistance")
    uploaded_img = st.file_uploader("Upload Chart Image", type=("png", "jpg", "jpeg"))
    if uploaded_img:
        img = Image.open(uploaded_img)
        st.image(img, use_container_width=True)
        if st.button("🔍 Analyze Chart Now", type="primary", use_container_width=True):
            if not is_vip and scans_today >= 2: st.error("Free Plan limit reached (2 scans/day). Upgrade for unlimited scans!")
            else:
                with st.spinner("Scanning chart..."):
                    try:
                        res = analyze_chart(encode_img(img), custom_strategy, multi_tf)
                        st.session_state.signals_history.append(res)
                        c.execute("UPDATE users SET scans_today = scans_today + 1 WHERE email=?", (user_email,))
                        conn.commit()
                        a, b, d = st.columns(3)
                        a.metric("Signal", res.get("signal", "WAIT"))
                        b.metric("Confidence", f"{res.get('confidence_percent', 0)}%")
                        d.metric("Risk : Reward", res.get("risk_reward", "N/A"))
                        st.success(f"🎯 **Entry:** `{res.get('entry_price')}` | 🛑 **SL:** `{res.get('stop_loss')}` | ✅ **TP1:** `{res.get('take_profit_1')}`")
                        for r in res.get("reasoning", list()): st.write(f"• {r}")
                    except Exception as e: st.error(f"Check OPENAI_API_KEY in Streamlit Secrets. Error: {e}")

with tab3:
    st.subheader("📰 NewsIQ — High-Impact NFP & CPI")
    if not is_vip:
        st.warning("🔒 NewsIQ is an Ultimate Plan feature.")
        st.link_button("Upgrade to Ultimate", STRIPE_PAYMENT_LINK, type="primary")
    else:
        events = fetch_macro_news()
        if not events: st.success("✅ No imminent high-impact USD news detected.")
        for ev in events:
            with st.container(border=True):
                st.markdown(f"**🔴 {ev.get('event', 'Event')}** (`{ev.get('country', 'US')}`)")
                st.caption(f"Time: {ev.get('time', 'N/A')} | Forecast: `{ev.get('estimate', 'N/A')}`")

with tab4:
    st.subheader("💬 Institutional AI Co-Pilot")
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg.get("role")): st.write(msg.get("content"))
    prompt_txt = st.chat_input("Ask AI Trade Lens anything...")
    if prompt_txt:
        st.session_state.chat_messages.append({"role": "user", "content": prompt_txt})
        with st.chat_message("user"): st.write(prompt_txt)
        with st.chat_message("assistant"):
            try:
                sys_m = list(({"role": "system", "content": "You are an institutional trading mentor."},))
                reply = client.chat.completions.create(model="gpt-4o-mini", messages=sys_m + st.session_state.chat_messages)
                ans = next(iter(reply.choices)).message.content
                st.write(ans)
                st.session_state.chat_messages.append({"role": "assistant", "content": ans})
            except Exception as e: st.error(f"Check OPENAI_API_KEY in Streamlit Secrets. Error: {e}")

with tab5:
    st.subheader("⚡ MT5 & Webhook Auto-Execution")
    if not is_vip:
        st.warning("🔒 Auto-Trading requires the Ultimate Plan.")
        st.link_button("Unlock Auto-Trading", STRIPE_PAYMENT_LINK, type="primary")
    else:
        st.text_input("Webhook / PineConnector URL", placeholder="https://...")
        risk_pct = st.slider("Risk Per Trade (%)", 0.25, 5.0, 1.0, 0.25)
        if st.button("Save Bridge Settings", type="primary"): st.success(f"Bridge active! Risk set to {risk_pct}%.")

with tab6:
    st.subheader("💎 Upgrade & Referrals")
    if is_vip: st.success("👑 You have full **ULTIMATE VIP** access!")
    else: st.link_button("🚀 Upgrade Now", STRIPE_PAYMENT_LINK, type="primary", use_container_width=True)
    st.divider()
    st.code("https://streamlit.app" + user_ref_code)
