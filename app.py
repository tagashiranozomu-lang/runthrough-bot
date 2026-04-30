import streamlit as st
import base64
import requests
from google import genai
from google.genai import types
from streamlit_mic_recorder import mic_recorder

API_KEY = st.secrets["GEMINI_API_KEY"]
GAS_SEARCH_URL = "https://script.google.com/macros/s/AKfycbwamDpiWCntQ2DMrg8uI7vvTby4LCMfsbbmrsQzvAvKY0kxhOZzAZQJ-KftIg2jRsTS/exec"
client = genai.Client(api_key=API_KEY)

PERSONA_BASE = """あなたは営業の練習相手です。以下のルールを守ってください。
- 相手の説明が不十分なら「もっと具体的に」「数字は？」と短く返す
- 一度に複数の質問を投げない（1つずつ深く詰める）
- プレゼンが終わったら「総評」として良かった点1つ・改善点3つを出す
- 日本語で話す"""

PERSONA_STRICT = """あなたは「最も厳しい決裁者」として振る舞います。
- 多忙。無駄な話は一切聞かない
- 数値・根拠のない話は即切り捨てる
- 「結局いくらかかるの？」「ROIは？」「他社と何が違うの？」を常に問う
- 弱点を見つけたら容赦なく突く
- 感情的にならず、論理で詰める
- 滅多に「いいね」と言わない
- 決裁者として質問・反論のみ行う
- 一度に複数の質問を投げない（1つずつ深く詰める）
- プレゼンが終わったら「総評」として良かった点1つ・改善点3つを出す
- 日本語で話す"""

st.set_page_config(page_title="ランスルーBot", page_icon="🎯")
st.title("🎯 ランスルーBot")

mode = st.sidebar.radio(
    "モードを選択",
    ["③ 最厳決裁者モード", "① 対人攻略モード", "② 新規提案練習モード"]
)

GITHUB_RAW_URL = "https://raw.githubusercontent.com/tagashiranozomu-lang/runthrough-bot/main/logs_index.json"

@st.cache_data(ttl=3600)
def load_logs_index():
    res = requests.get(GITHUB_RAW_URL, timeout=60)
    return res.json()

def fetch_logs(query, search_mode):
    try:
        all_logs = load_logs_index()
        query_lower = query.lower()
        results = []
        for log in all_logs:
            if query_lower in log["filename"].lower() or query_lower in log["content"].lower():
                results.append({"filename": log["filename"], "content": log["content"]})
            if len(results) >= 5:
                break
        return results
    except Exception as e:
        st.error(f"ログ取得エラー: {e}")
    return []

def build_persona_from_logs(logs, query, mode):
    combined = "\n\n".join([f"=== {f['filename']} ===\n{f['content'][:1500]}" for f in logs[:3]])
    if mode == "person":
        prompt = f"""以下の商談ログから「{query}」の担当者プロファイルを作成してください。

## ログ
{combined}

## 人物カルテ（必ずこの形式で）
- **人柄・コミュニケーションスタイル**:
- **好まれる言い回し・キーワード**:
- **懸念・こだわりポイント**:
- **意思決定スタイル**:
- **NGワード・避けるべき話し方**:

## このペルソナとして練習する際の注意点
-
"""
    else:
        prompt = f"""以下の商談ログから「{query}」業界の新規提案でよく出る厳しい質問・反論パターンを分析してください。

## ログ
{combined}

## よく出る質問・反論トップ5
1.
2.
3.
4.
5.

## この業界特有の地雷・注意点
-

## このデータをもとに練習する際の心構え
-
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        ),
    )
    return response.text

def get_bot_reply(user_text, persona, history):
    contents = []
    for msg in history:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_text}]})
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=persona,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return response.text

def handle_input(user_text, persona):
    st.session_state.history.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.write(f"【あなた】　{user_text}")
    with st.chat_message("assistant"):
        with st.spinner("考えています..."):
            reply = get_bot_reply(user_text, persona, st.session_state.history[:-1])
        st.write(f"【決裁者】　{reply}")
    st.session_state.history.append({"role": "assistant", "content": reply})

def show_chat_ui(persona):
    for msg in st.session_state.history:
        label = "【決裁者】" if msg["role"] == "assistant" else "【あなた】"
        with st.chat_message(msg["role"]):
            st.write(f"{label}　{msg['content']}")

    st.markdown("---")
    audio = mic_recorder(start_prompt="🎤 話す", stop_prompt="⏹ 送信", just_once=True, key="mic")
    if audio:
        audio_b64 = base64.b64encode(audio["bytes"]).decode()
        with st.spinner("音声認識中..."):
            tr = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[{"role": "user", "parts": [
                    {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}},
                    {"text": "この音声を文字起こしして、結果のみ返してください。"}
                ]}],
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                ),
            )
            transcript = tr.text.strip()
        handle_input(transcript, persona)
        st.rerun()

    user_input = st.chat_input("テキストで入力...")
    if user_input:
        handle_input(user_input, persona)
        st.rerun()

# ========== モード別UI ==========

if mode == "③ 最厳決裁者モード":
    st.caption("汎用の最厳決裁者と練習します")
    if "history" not in st.session_state or st.session_state.get("last_mode") != mode:
        st.session_state.history = [{"role": "assistant", "content": "では始めてください。何の提案ですか？"}]
        st.session_state.last_mode = mode
    show_chat_ui(PERSONA_STRICT)

elif mode == "① 対人攻略モード":
    st.caption("特定の担当者のペルソナで練習します")
    query = st.text_input("担当者名または会社名を入力", placeholder="例：タイミー、田中様")

    if query and st.button("ログを検索してカルテ生成"):
        with st.spinner(f"「{query}」のログを検索中..."):
            logs = fetch_logs(query, "person")
        if logs:
            st.success(f"{len(logs)}件のログが見つかりました")
            with st.spinner("人物カルテを生成中..."):
                karte = build_persona_from_logs(logs, query, "person")
            st.session_state.karte = karte
            st.session_state.logs_persona = PERSONA_BASE + f"\n\n以下の人物カルテを参考に、この担当者として振る舞ってください：\n{karte}"
            st.session_state.history = [{"role": "assistant", "content": f"「{query}」担当者のペルソナで練習します。では始めてください。"}]
            st.session_state.last_mode = mode
        else:
            st.warning("該当するログが見つかりませんでした")

    if "karte" in st.session_state and st.session_state.get("last_mode") == mode:
        with st.expander("📋 人物カルテを見る"):
            st.markdown(st.session_state.karte)
        show_chat_ui(st.session_state.logs_persona)

elif mode == "② 新規提案練習モード":
    st.caption("類似業界のログをもとに厳しい質問で練習します")
    query = st.text_input("業界キーワードを入力", placeholder="例：教育、人材、SaaS、製造")

    if query and st.button("ログを検索して練習開始"):
        with st.spinner(f"「{query}」業界のログを検索中..."):
            logs = fetch_logs(query, "industry")
        if logs:
            st.success(f"{len(logs)}件のログが見つかりました")
            with st.spinner("業界分析中..."):
                analysis = build_persona_from_logs(logs, query, "industry")
            st.session_state.analysis = analysis
            st.session_state.logs_persona = PERSONA_STRICT + f"\n\n以下の業界分析をもとに、この業界特有の厳しい質問を重点的に行ってください：\n{analysis}"
            st.session_state.history = [{"role": "assistant", "content": f"「{query}」業界の新規提案練習を始めます。では提案をどうぞ。"}]
            st.session_state.last_mode = mode
        else:
            st.warning("該当するログが見つかりませんでした")

    if "analysis" in st.session_state and st.session_state.get("last_mode") == mode:
        with st.expander("📊 業界分析を見る"):
            st.markdown(st.session_state.analysis)
        show_chat_ui(st.session_state.logs_persona)
