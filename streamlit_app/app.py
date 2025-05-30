import streamlit as st
from st_audiorec import st_audiorec
import requests, base64, time, threading
import os
from dotenv import load_dotenv

load_dotenv()

FASTAPI_HOST = os.getenv("FASTAPI_HOST")
TRANSCRIBE_URL = f"{FASTAPI_HOST}/transcribe/"
MCP_URL        = f"{FASTAPI_HOST}/mcp/"
ANSWER_URL     = f"{FASTAPI_HOST}/answer/"

st.set_page_config(page_title="Market Analyst AI", page_icon="🎙️", layout="centered")
st.title("Market Analyst AI")
st.markdown("Powered by Voice, LLM's, RAG, and Financial APIs")

# ─────────────── Quick-start helper text (place after st.caption) ─────────────── #
st.markdown(
    """
    <div style="
        border:1px solid #e7e7e7;
        border-radius:6px;
        padding:14px 16px;
        font-size:16px;
        line-height:1.45;">
        
      <p style="margin:0 0 8px 0;font-weight:600;">Quick guide</p>
      
      <ol style="margin:0 0 8px 18px;padding:0;">
        <li>Click the mic</strong> &nbsp;to start recording</li>
        <li>Ask any market-related question and hit stop</li>
        <li>We’ll transcribe your query and detect its intent</li>
        <li>Read the latest news about that stock while data loads</li>
        <li>Read or listen to the answer when it appears</li>
      </ol>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("##### Try with Sample Prompts")

cols = st.columns(2)

prompt_map = {
    "What is Nike's stock price today, and should I invest in it?": "prompt_1.wav",
    "Summarize Apple's earnings and news highlights.": "prompt_2.wav",
    "What's the sentiment around Tesla this month?": "prompt_3.wav",
    "Compare Samsung and AMD for the past 3 months.": "prompt_4.wav",
    "Show Google's risk analysis and key shareholders.": "prompt_5.wav",
    "What is Microsoft's option chain insight?": "prompt_6.wav",
}

custom_button_css = """
<style>
div.stButton > button {
    width: 100%;
    height: 60px;
    border-radius: 6px;
    font-size: 15px;
}
</style>
"""

st.markdown(custom_button_css, unsafe_allow_html=True)

for i, (label, file_name) in enumerate(prompt_map.items()):
    col = cols[i % 2]
    with col:
        if st.button(label):
            file_path = os.path.join("streamlit_app", "prompts", file_name)
            with open(file_path, "rb") as f:
                audio_bytes = f.read()
            st.session_state["audio_bytes"] = audio_bytes
            st.toast("Scroll down to view the results")


def autoplay_audio(path: str):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    st.markdown(
        f"""
        <audio controls autoplay>
          <source src="data:audio/wav;base64,{b64}" type="audio/wav">
        </audio>""",
        unsafe_allow_html=True,
    )

def headline_html(ticker: str, art: dict) -> str:
    title   = art.get("Title",   "No Title")
    summary = art.get("Summary", "No Summary")
    url     = art.get("URL",     "#")
    return f"""
    <h4 style="margin:0 0 6px 0;">What’s making headlines…</h4>
    <div style="padding:10px;border:1px solid #e1e1e1;border-radius:6px;">
      <strong>{ticker} in the news:</strong><br>
      <span style="color:#f39c12;font-size:18px;">{title}</span><br>
      <span style="font-size:14px;">{summary}</span><br>
      <a href="{url}" target="_blank">Read full article ↗︎</a>
    </div>
    """

st.markdown("### Record Your Query")

audio_bytes = None
transcript = None
intent = None

# 🔁 Mic recording (separate)
audio_from_mic = st_audiorec()
if audio_from_mic:
    st.session_state["audio_bytes"] = audio_from_mic
    st.toast("Scroll down to view the results 🔽")

# 🧠 Transcribe and classify (only once)
if "audio_bytes" in st.session_state:
    audio_bytes = st.session_state.pop("audio_bytes")

    st.markdown("### Transcribe & Understand Your Query")
    with st.spinner("Transcribing and classifying intent…"):
        tr = requests.post(
            TRANSCRIBE_URL,
            files={"file": ("audio.wav", audio_bytes, "audio/wav")},
        )

    if tr.status_code != 200:
        st.error("Failed to get transcript and intent.")
        st.stop()

    data        = tr.json()
    transcript  = data.get("transcript", "")
    intent      = data.get("intent", {})
    ticker_list   = intent.get("tickers", [])
    ticker_name   = (ticker_list[0] if ticker_list else intent.get("ticker", "This stock")).upper()

    tabs = st.tabs(["Transcript", "Intent"])
    with tabs[0]:
        st.markdown(f"**You said:**\n> {transcript}")
    with tabs[1]:
        st.json(intent)

    st.markdown("### Fetching Structured Market Data")
    with st.spinner("Calling MCP agent…"):
        mcp_r = requests.post(MCP_URL, json={"transcript": transcript, "intent": intent})
    if mcp_r.status_code != 200:
        st.warning("Failed to retrieve MCP output."); st.stop()

    mcp_data = mcp_r.json()
    st.markdown("MCP Data Retrieved Successfully")
    with st.expander("View Raw MCP Data"):
        st.json(mcp_data)

    st.markdown("### Generating Final Answer")
    carousel_box = st.empty()
    answer_box   = st.empty()

    done_evt   = threading.Event()
    answer_res = {}

    def fetch_answer():
        global answer_res
        try:
            resp = requests.post(
                ANSWER_URL,
                json={"transcript": transcript, "intent": intent, "mcp_data": mcp_data},
                timeout=None,
            )
            if resp.status_code == 200:
                answer_res = resp.json()
        finally:
            done_evt.set()

    threading.Thread(target=fetch_answer, daemon=True).start()

    articles = mcp_data.get("data", {}).get("news_summary", [])
    idx = 0
    while not done_evt.is_set():
        if articles:
            carousel_box.markdown(
                headline_html(ticker_name, articles[idx % len(articles)]),
                unsafe_allow_html=True,
            )
            idx += 1
        time.sleep(7)

    carousel_box.empty()
    answer_text = answer_res.get("answer", "")
    audio_data  = answer_res.get("audio", "")   # data URL

    answer_box.markdown("## V.E.R.O.N.I.C.A's Answer")
    answer_box.markdown(answer_text)

    if audio_data:                                      # data:audio/wav;base64,…
        st.markdown(
            f"""
            <audio controls autoplay style="width:100%;outline:none;">
                <source src="{audio_data}" type="audio/wav">
                Your browser does not support the audio element.
            </audio>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.warning("No audio response available.")

    st.toast("Response generated, scroll down to view it")