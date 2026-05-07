import streamlit as st
import base64
import requests
import json
import re
from google import genai
from google.genai import types
from streamlit_mic_recorder import mic_recorder

API_KEY = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=API_KEY)

GITHUB_RAW_URL = "https://raw.githubusercontent.com/tagashiranozomu-lang/runthrough-bot/main/logs_index.json"

APO_PURPOSES = [
    "初回商談でニーズを引き出す",
    "次回提案の機会を獲得する",
    "本提案・クロージングを行う",
    "既存顧客の継続・更新を確保する",
    "アップセル・クロスセルを提案する",
    "失注後の関係を再構築する",
    "競合からの乗り換えを提案する",
    "予算・稟議承認を獲得する",
    "導入後の課題をヒアリングし改善提案する",
    "新たなキーパーソンと関係を構築する",
    "その他（自由記述）",
]

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

CUSTOMER_TYPES_16 = """
【顧客16タイプ一覧】

＜主導型グループ＞
タイプ1「成果主導型」：数字・結果にフォーカス。ROI・KPIで判断する。「で、結果は？」が口癖。
タイプ2「革新主導型」：新しいことに積極的。トレンドや先進事例に強く興味を持つ。
タイプ3「競争主導型」：競合他社との差別化を強く意識する。「他社と何が違う？」が口癖。
タイプ4「権威主導型」：自分の経験・判断を最重視。上から目線になりやすく、従来のやり方を変えたがらない。

＜感化型グループ＞
タイプ5「熱狂型」：ビジョン・熱量で動く。感情的に共鳴すると一気に動く。
タイプ6「共感型」：相手の話をよく聞く。人間関係・信頼を大切にする。
タイプ7「影響力型」：社内評判・他者の目を気にする。実績・推薦事例に弱い。
タイプ8「楽観型」：リスクより可能性に目を向ける。細かい話より夢の話が好き。

＜安定型グループ＞
タイプ9「協調型」：チーム・社内合意を重視。一人では決めない。「上に相談します」が口癖。
タイプ10「信頼重視型」：長期的な関係・信頼を最優先にする。人で買う。
タイプ11「保守型」：現状維持志向。変化・リスクを極端に嫌う。「今のままでいい」が口癖。
タイプ12「サポート型」：自分より他者・チームを優先。縁の下の力持ち。意思決定より実務を好む。

＜分析型グループ＞
タイプ13「完璧主義型」：細部・正確性にこだわる。資料の粗が気になる。「この数字の根拠は？」が口癖。
タイプ14「懐疑型」：疑問・検証を繰り返す。「本当に？」「証拠は？」が口癖。
タイプ15「戦略型」：長期的視点・全体像で判断。部分最適より全体最適を重視。
タイプ16「専門家型」：業界知識・専門性を重視。浅い話を嫌う。用語・深度で信頼度を測る。
"""

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
    keywords = set()
    # Split query into individual words so "タイミー 田中" matches files containing either word
    parts = query.split()
    for part in parts:
        keywords.add(part)
        part_lower = part.lower()
        for key, synonyms in KEYWORD_EXPAND.items():
            if any(s.lower() in part_lower or part_lower in s.lower() for s in synonyms):
                keywords.update(synonyms)
    return list(keywords)

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

def extract_persons_from_company(company_query):
    try:
        all_logs = load_logs_index()
        keywords = expand_keywords(company_query)
        persons = set()
        for log in all_logs:
            if any(kw.lower() in log["filename"].lower() for kw in keywords):
                matches = re.findall(r'\d+:\d+\s+([^\n]{2,20})', log["content"])
                for name in matches[:30]:
                    name = name.strip()
                    if name and not name[0].isdigit() and 2 <= len(name) <= 20:
                        persons.add(name)
        return sorted(list(persons))
    except:
        return []

def call_gemini(prompt):
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
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

def build_runthrough_persona(logs, query):
    combined = "\n\n".join([f"=== {f['filename']} ===\n{f['content'][:1500]}" for f in logs[:3]])
    prompt = f"""以下の「{query}」業界の商談ログを分析し、この業界の典型的な顧客担当者・決裁者のペルソナを作成してください。

## ログ
{combined}

## 出力形式（必ずこの形式で）

### 業界顧客ペルソナ
- **典型的な役職・立場**:
- **コミュニケーションスタイル**:
- **よく使う言葉・フレーズ**:
- **主な関心事・懸念点**:
- **意思決定の傾向**:
- **典型的な質問・反論**:
"""
    persona_profile = call_gemini(prompt)

    persona_instruction = f"""あなたは「{query}」業界の顧客担当者・決裁者として振る舞います。

以下のペルソナに忠実に、リアルな顧客として応答してください。

{persona_profile}

【ルール】
- このペルソナのコミュニケーションスタイルで話す
- 一度に複数の質問を投げない（1つずつ深く詰める）
- 営業の説明が不十分なら具体化を求める
- プレゼンが終わったら「総評」として良かった点1つ・改善点3つを出す
- 日本語で話す"""

    return persona_profile, persona_instruction

def generate_feedback(history, karte):
    transcript = ""
    for msg in history:
        if msg["role"] == "user":
            transcript += f"【営業】{msg['content']}\n"
        elif msg["role"] == "assistant":
            transcript += f"【顧客】{msg['content']}\n"

    prompt = f"""以下は営業ロープレの会話記録です。営業担当者のパフォーマンスを評価してください。

## 顧客カルテ（顧客設定）
{karte}

## ロープレ会話
{transcript}

## フィードバック（必ずこの形式で）

### ✅ 良かった点
1.
2.
3.

### ⚠️ 改善点
1.
2.
3.

### 💡 次回への具体的なアドバイス
-
-
-

### 総合評価：○○点／100点
理由：
"""
    return call_gemini(prompt)

def generate_runthrough_score(history):
    transcript = ""
    for msg in history:
        if msg["role"] == "user":
            transcript += f"【営業】{msg['content']}\n"
        elif msg["role"] == "assistant":
            transcript += f"【決裁者】{msg['content']}\n"

    prompt = f"""以下は新規提案ランスルーの会話記録です。営業担当者を項目別に採点してください。

## ランスルー会話
{transcript}

## 採点結果（必ずこの形式で）

### 📊 項目別採点

| 項目 | 点数（/20点） | コメント |
|------|-------------|---------|
| 課題理解（顧客の状況・痛みを正確に把握できたか） | /20 | |
| ROI・数字説明（投資対効果を具体的に示せたか） | /20 | |
| 競合差別化（他社と何が違うかを答えられたか） | /20 | |
| 反論対応（厳しい突っ込みに論理で返せたか） | /20 | |
| 端的さ（無駄なく結論から話せたか） | /20 | |

### 🏆 総合得点：○○点／100点

### ✅ 特に良かった点
-

### ⚠️ 最優先の改善点
-

### 💡 次回ランスルーへの一言アドバイス
"""
    return call_gemini(prompt)

def generate_apo_design(purpose, query, logs):
    combined = "\n\n".join([f"=== {f['filename']} ===\n{f['content'][:1500]}" for f in logs[:5]])
    logs_section = combined if combined else "（関連ログなし：一般的な知識で判断）"
    prompt = f"""あなたは営業戦略のエキスパートです。
以下の情報をもとに、アポ設計シートを作成してください。

## アポの目的
{purpose}

## 顧客・担当者情報
{query}

## 過去の類似商談ログ
{logs_section}

{CUSTOMER_TYPES_16}

## 出力形式（必ずこの形式・この順番で）

### 👥 顧客タイプ分析
過去ログと顧客情報をもとに、上記16タイプの中から最も該当するタイプを判定してください。

**メインタイプ：タイプ〇「〇〇型」**
判定理由：（ログや業界特性から読み取れる根拠を2〜3文で）

**サブタイプ：タイプ〇「〇〇型」**（該当する場合のみ）
理由：

---

### 🎯 道筋シナリオ
判定タイプを踏まえた3つのアプローチパターン

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

# ========== セットアップ ==========

st.set_page_config(page_title="アポドリル", page_icon="⚡")
st.title("⚡ アポドリル")

MODES = ["① アポ設計モード", "② 対人攻略モード", "③ 新規ランスルーモード"]
if "mode_index" not in st.session_state:
    st.session_state.mode_index = 0

mode = st.sidebar.radio("モードを選択", MODES, index=st.session_state.mode_index)
st.session_state.mode_index = MODES.index(mode)

# ========== ① アポ設計モード ==========

if mode == "① アポ設計モード":
    st.caption("アポ前の準備シートを自動生成します")

    purpose_choice = st.selectbox("このアポで達成したい目的を選択", APO_PURPOSES)
    if purpose_choice == "その他（自由記述）":
        purpose = st.text_area("目的を自由記述してください", height=80)
    else:
        purpose = purpose_choice

    company = st.text_input("会社名を入力", placeholder="例：タイミー、三幸学園")

    person_query = company
    if company:
        with st.spinner("担当者を検索中..."):
            persons = extract_persons_from_company(company)

        if persons:
            person_options = ["（全員／会社全体で検索）"] + persons
            selected_person = st.selectbox("先方担当者を選択", person_options)
            if selected_person != "（全員／会社全体で検索）":
                person_query = f"{company} {selected_person}"
        else:
            st.info("担当者名が見つかりませんでした。会社名で検索します。")

    if purpose and company and st.button("アポ設計シートを生成"):
        with st.spinner(f"「{person_query}」の過去ログを検索中..."):
            logs = fetch_logs(person_query, "industry")
        if logs:
            st.success(f"{len(logs)}件の関連ログをもとに生成します")
        else:
            st.info("関連ログは見つかりませんでしたが、一般的な知識で生成します")

        with st.spinner("アポ設計シートを生成中..."):
            sheet = generate_apo_design(purpose, person_query, logs)

        st.session_state.apo_sheet = sheet
        st.session_state.apo_query = person_query
        st.session_state.apo_purpose = purpose
        st.session_state.last_mode = mode

    if "apo_sheet" in st.session_state and st.session_state.get("last_mode") == mode:
        st.markdown("---")
        st.markdown(st.session_state.apo_sheet)
        st.markdown("---")
        st.markdown("### 🚀 このままロープレに進む")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("② 対人攻略モードで練習する", use_container_width=True):
                st.session_state.pre_query = st.session_state.apo_query
                st.session_state.pre_purpose = st.session_state.apo_purpose
                st.session_state.trigger_mode2 = True
                st.session_state.mode_index = 1
                st.rerun()
        with col2:
            if st.button("③ 新規ランスルーモードで練習する", use_container_width=True):
                st.session_state.pre_query = st.session_state.apo_query
                st.session_state.pre_purpose = st.session_state.apo_purpose
                st.session_state.trigger_mode3 = True
                st.session_state.mode_index = 2
                st.rerun()

# ========== ② 対人攻略モード ==========

elif mode == "② 対人攻略モード":
    st.caption("特定の担当者のペルソナで練習します")

    pre_query = st.session_state.pop("pre_query", "") if st.session_state.get("trigger_mode2") else ""
    trigger = st.session_state.pop("trigger_mode2", False)

    query = st.text_input("担当者名または会社名を入力", value=pre_query, placeholder="例：タイミー、田中様")

    if (trigger and query) or (query and st.button("ログを検索してカルテ生成")):
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

        if len(st.session_state.get("history", [])) > 2:
            st.markdown("---")
            if st.button("📝 ロープレ終了・フィードバックをもらう", use_container_width=True):
                with st.spinner("フィードバックを生成中..."):
                    st.session_state.feedback = generate_feedback(
                        st.session_state.history,
                        st.session_state.karte,
                    )

        if "feedback" in st.session_state and st.session_state.get("last_mode") == mode:
            st.markdown("---")
            st.markdown("## 📊 ロープレフィードバック")
            st.markdown(st.session_state.feedback)

# ========== ③ 新規ランスルーモード ==========

elif mode == "③ 新規ランスルーモード":
    st.caption("類似業界のログをもとに厳しい決裁者と練習します")

    pre_query = st.session_state.pop("pre_query", "") if st.session_state.get("trigger_mode3") else ""
    trigger = st.session_state.pop("trigger_mode3", False)

    query = st.text_input("業界キーワードを入力", value=pre_query, placeholder="例：教育、人材、SaaS、製造")

    if (trigger and query) or (query and st.button("ログを検索して練習開始")):
        with st.spinner(f"「{query}」業界のログを検索中..."):
            logs = fetch_logs(query, "industry")
        if logs:
            st.success(f"{len(logs)}件のログが見つかりました")
            with st.spinner("業界ペルソナを生成中..."):
                analysis, persona_instruction = build_runthrough_persona(logs, query)
            st.session_state.analysis = analysis
            st.session_state.logs_persona = persona_instruction
            st.session_state.history = [{"role": "assistant", "content": f"「{query}」業界の顧客として練習します。では提案をどうぞ。"}]
            st.session_state.last_mode = mode
            st.session_state.pop("runthrough_score", None)
        else:
            st.warning("該当するログが見つかりませんでした")

    if "analysis" in st.session_state and st.session_state.get("last_mode") == mode:
        with st.expander("📊 業界分析を見る"):
            st.markdown(st.session_state.analysis)
        show_chat_ui(st.session_state.logs_persona)

        if len(st.session_state.get("history", [])) > 2:
            st.markdown("---")
            if st.button("🏆 ランスルー終了・採点してもらう", use_container_width=True):
                with st.spinner("採点中..."):
                    st.session_state.runthrough_score = generate_runthrough_score(
                        st.session_state.history
                    )

        if "runthrough_score" in st.session_state and st.session_state.get("last_mode") == mode:
            st.markdown("---")
            st.markdown("## 🏆 ランスルー採点結果")
            st.markdown(st.session_state.runthrough_score)
