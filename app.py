import streamlit as st
from google import genai
from google.genai import types

API_KEY = "AIzaSyDa2ahdCEbKZREevcIQM_MKMuq4aPPMCDo"
client = genai.Client(api_key=API_KEY)

PERSONA = """あなたは「最も厳しい決裁者」として振る舞います。

【ペルソナ】
- 多忙。無駄な話は一切聞かない
- 数値・根拠のない話は即切り捨てる
- 「結局いくらかかるの？」「ROIは？」「他社と何が違うの？」を常に問う
- 弱点を見つけたら容赦なく突く
- 感情的にならず、論理で詰める
- 滅多に「いいね」と言わない

【ルール】
- 決裁者として質問・反論のみ行う
- 相手の説明が不十分なら「もっと具体的に」「数字は？」と短く返す
- 一度に複数の質問を投げない（1つずつ深く詰める）
- プレゼンが終わったら「総評」として良かった点1つ・改善点3つを出す
- 日本語で話す"""

st.set_page_config(page_title="ランスルーBot｜最厳決裁者モード", page_icon="🎯")
st.title("🎯 ランスルーBot｜最厳決裁者モード")
st.caption("声でプレゼンしてください。決裁者が厳しく問い返します。")

if "history" not in st.session_state:
    st.session_state.history = []
    st.session_state.history.append({
        "role": "assistant",
        "content": "では始めてください。何の提案ですか？"
    })

for msg in st.session_state.history:
    role = "【決裁者】" if msg["role"] == "assistant" else "【あなた】"
    with st.chat_message(msg["role"]):
        st.write(f"{role}　{msg['content']}")

st.info("🎤 下のテキストボックスに話した内容を入力 または マイクボタンで音声入力（Chrome推奨）")

user_input = st.chat_input("プレゼン内容を入力してください...")

if user_input:
    st.session_state.history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(f"【あなた】　{user_input}")

    with st.chat_message("assistant"):
        with st.spinner("決裁者が考えています..."):
            contents = []
            for msg in st.session_state.history:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=PERSONA),
            )
            reply = response.text
            st.write(f"【決裁者】　{reply}")

    st.session_state.history.append({"role": "assistant", "content": reply})
    st.rerun()
