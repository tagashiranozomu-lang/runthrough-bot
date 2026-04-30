import streamlit as st
import base64
import requests
import json
from google import genai
from google.genai import types
from streamlit_mic_recorder import mic_recorder

API_KEY = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=API_KEY)

GITHUB_RAW_URL = "https://raw.githubusercontent.com/tagashiranozomu-lang/runthrough-bot/main/logs_index.json"

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

st.set_page_config(page_title="アポDRILL", page_icon="🎯")
st.title("🎯 アポDRILL")

mode = st.sidebar.radio(
    "モードを選択",
    ["① アポ設計モード", "② 対人攻略モード", "③ 新規提案練習モード"]
)

KEYWORD_EXPAND = {
    "人材": ["人材", "採用", "求人", "HR", "人事", "リクルート", "転職"],
    "教育": ["教育", "研修", "学習", "eラーニング", "スクール", "トレーニング"],
    "SaaS": ["SaaS", "クラウド", "システム", "ツール", "プラットフォーム"],
    "製造": ["製造", "メーカー", "工場", "生産", "品質管理"],
    "不動産": ["不動産", "建設", "住宅", "マンション", "土地"],
    "医療": ["医療", "病院", "クリニック", "ヘルスケア", "製薬"],
    "金融": ["金融", "銀行", "保険", "証券", "投資", "FinTech"],
    "小売": ["小売", "EC", "通販", "流通", "店舗"],
    "飲食": ["飲食", "レストラン", "フード", "外食"],
    "IT": ["IT", "システム", "エンジニア", "開発", "DX", "デジタル"],
}

def expand_keywords(query):
    keywords = [query]
    query_lower = query.lower()
    for key, synonyms in KEYWORD_EXPAND.items():
        if any(s.lower() in query_lower or query_lower in s.lower() for s in synonyms):
            keywords.extend(synonyms)
    return list(set(keywords))

@st.cache_data(ttl=3600)
def load_logs_index():
    res = requests.get(GITHUB_RAW_URL, timeout=60)
    res.encoding = "utf-8"
    return json.loads(res.text)

def fetch_logs(query, search_mode):
    try:
        all_logs = load_logs_index()
        keywords = expand_keywords(query)
        scored = []
        for log in all_logs:
            text = (log["filename"] + " " + log["content"]).lower()
            score = sum(1 for kw in keywords if kw.lower() in text)
            if score > 0:
                scored.append((score, log))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [log for _, log in scored[:5]]
    except Exception as e:
        st.error(f"ログ取得エラー: {e}")
    return []

def call_gemini(prompt):
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        ),
    )
    return response.text

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

## 練習時の注意点
-
"""
    else:
        prompt = f"""以下の商談ログから「{query}」業界の新規提案でよく出る質問・反論パターンを分析してください。

## ログ
{combined}

## よく出る質問・反論トップ5
1.
2.
3.
4.
5.

## この業界特有の注意点
-
"""
    return call_gemini(prompt)

CUSTOMER_TYPES = """
【顧客タイプ一覧】
タイプ1「数値重視型」：ROI・具体的な数字・実績データを強く求める。感情より論理で動く。「それで結果は？」「数字で見せて」が口癖。
タイプ2「リスク回避型」：失敗・変化を恐れる。導入実績・保証・サポート体制を重視する。「他社での失敗事例は？」「もし上手くいかなかったら？」が口癖。
タイプ3「関係構築型」：担当者との信頼関係・人間性を最優先にする。感情で動く。「あなたを信頼しているから」が決め手になる。
タイプ4「スピード重視型」：即断即決を好む。結論から話すことを求める。回りくどい説明を嫌う。「で、要するに何が言いたいの？」が口癖。
タイプ5「慎重検討型」：社内稟議・合議を重視。独断では決めない。決定まで時間がかかる。「一度持ち帰って検討します」が口癖。
"""

def generate_apo_design(purpose, query, logs):
    combined = "\n\n".join([f"=== {f['filename']} ===\n{f['content'][:1500]}" for f in logs[:5]])
    logs_section = combined if combined else "（関連ログなし：一般的な知識で判断）"

    prompt = f"""あなたは営業戦略のエキスパートです。
以下の情報をもとに、アポ設計シートを作成してください。

## アポの目的
{purpose}

## 顧客・業界情報
{query}

## 過去の類似商談ログ
{logs_section}

{CUSTOMER_TYPES}

## 出力形式（必ずこの形式・この順番で）

### 👥 顧客タイプ分析
過去ログと顧客情報をもとに、上記5タイプの中から最も該当するタイプを1〜2個判定してください。

**判定結果：タイプ〇「〇〇型」**（可能性：高/中）
判定理由：（ログや業界特性から読み取れる根拠を2〜3文で）

**サブタイプ：タイプ〇「〇〇型」**（可能性：中）※該当する場合のみ
理由：

---

### 🎯 道筋シナリオ
上記タイプを踏まえた3つのアプローチパターン

**パターンA：**（アプローチ名）
- 流れ：
- このタイプへの有効ポイント：

**パターンB：**（アプローチ名）
- 流れ：
- このタイプへの有効ポイント：

**パターンC：**（アプローチ名）
- 流れ：
- このタイプへの有効ポイント：

---

### ⚡ 想定される突っ込みパターン
このタイプ・業界で特によく出る質問・反論を5つ

① 突っ込み内容：
　→ 返し方のヒント：

② 突っ込み内容：
　→ 返し方のヒント：

③ 突っ込み内容：
　→ 返し方のヒント：

④ 突っ込み内容：
　→ 返し方のヒント：

⑤ 突っ込み内容：
　→ 返し方のヒント：

---

### ✅ 準備チェックリスト
このタイプ・目的に合わせた準備項目5つ

- [ ] 
- [ ] 
- [ ] 
- [ ] 
- [ ] 
"""
    return call_gemini(prompt)

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
        st.write(f"【相手】　{reply}")
    st.session_state.history.append({"role": "assistant", "content": reply})

def show_chat_ui(persona):
    for msg in st.session_state.history:
        label = "【相手】" if msg["role"] == "assistant" else "【あなた】"
        with st.chat_message(msg["role"]):
            st.write(f"{label}　{msg['content']}")

    st.markdown("---")
    audio = mic_recorder(start_prompt="🎤 話す", stop_prompt="⏹ 送信", just_once=True, key="mic")
    if audio:
        audio_b64 = base64.b64encode(audio["bytes"]).decode()
        with st.spinner("音声認識中..."):
            transcript = call_gemini([{
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}},
                    {"text": "この音声を文字起こしして、結果のみ返してください。"}
                ]
            }])
        handle_input(transcript.strip(), persona)
        st.rerun()

    user_input = st.chat_input("テキストで入力...")
    if user_input:
        handle_input(user_input, persona)
        st.rerun()

# ========== モード別UI ==========

if mode == "① アポ設計モード":
    st.caption("アポ前の準備シートを自動生成します")

    purpose = st.text_area(
        "このアポで達成したい目的を入力",
        placeholder="例：初回商談でニーズを引き出し、次回の提案機会を獲得したい",
        height=100
    )
    query = st.text_input(
        "顧客名または業界キーワード",
        placeholder="例：タイミー、教育業界、SaaS"
    )

    if purpose and query and st.button("アポ設計シートを生成"):
        with st.spinner(f"「{query}」の過去ログを検索中..."):
            logs = fetch_logs(query, "industry")
        log_count = len(logs)
        if log_count > 0:
            st.success(f"{log_count}件の関連ログをもとに生成します")
        else:
            st.info("関連ログは見つかりませんでしたが、一般的な知識で生成します")

        with st.spinner("アポ設計シートを生成中..."):
            sheet = generate_apo_design(purpose, query, logs)

        st.session_state.apo_sheet = sheet
        st.session_state.apo_query = query
        st.session_state.last_mode = mode

    if "apo_sheet" in st.session_state and st.session_state.get("last_mode") == mode:
        st.markdown("---")
        st.markdown(st.session_state.apo_sheet)
        st.markdown("---")
        st.info("👇 この設計をもとに練習するには、左のメニューから①または②を選んでください")

elif mode == "② 対人攻略モード":
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

elif mode == "③ 新規提案練習モード":
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
