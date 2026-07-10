import streamlit as st
import anthropic
import os
import math

# ── ページ設定 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="求人原稿スコアリングアプリ",
    page_icon="📝",
    layout="wide",
)

# ── カスタムCSS ─────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=Inter:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans JP', 'Inter', sans-serif; }

.app-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
    border-radius: 12px;
    padding: 2rem 2.5rem;
    margin-bottom: 2rem;
    border-left: 4px solid #3b82f6;
}
.app-header h1 { color: #ffffff; font-size: 1.9rem; font-weight: 700; margin: 0 0 0.4rem 0; letter-spacing: -0.02em; }
.app-header p { color: #94a3b8; font-size: 0.9rem; margin: 0; }

.result-block {
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 1.8rem 2rem; margin-top: 1.0rem; margin-bottom: 2rem; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    line-height: 1.7;
}

.stButton > button {
    background: #3b82f6 !important; color: #ffffff !important; border: none !important;
    border-radius: 8px !important; font-weight: 600 !important; font-size: 1.05rem !important;
    padding: 0.8rem 2rem !important; width: 100% !important; transition: opacity 0.2s !important;
}
.stButton > button:hover { opacity: 0.88 !important; }
.reset-btn > button {
    background: #64748b !important; font-size: 0.9rem !important; padding: 0.5rem 1rem !important;
}
</style>
""", unsafe_allow_html=True)

# ── セッション状態の初期化（記憶機能） ─────────────────────────
if "current_step" not in st.session_state:
    st.session_state.current_step = 0
if "ai_messages" not in st.session_state:
    st.session_state.ai_messages = []
if "results" not in st.session_state:
    st.session_state.results = {}

# ── ヘッダー ────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <h1>📝 求人原稿 添削・スコアリングエージェント</h1>
    <p>AIの処理限界を防ぐため、1ステップずつ着実に分析と改善を行います</p>
</div>
""", unsafe_allow_html=True)

# ── APIキー確認 ─────────────────────────────────────────────────
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    except:
        st.error("⚠️ Anthropic APIキーが設定されていません。右上のSettings > Secretsから登録してください。")
        st.stop()

# ── リセットボタン ──────────────────────────────────────────────
st.markdown('<div class="reset-btn">', unsafe_allow_html=True)
if st.button("🔄 別の原稿を評価する（システムをリセット）"):
    st.session_state.current_step = 0
    st.session_state.ai_messages = []
    st.session_state.results = {}
    st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

# ── 入力フォーム ────────────────────────────────────────────────
col_left, col_right = st.columns([1, 1.5], gap="large")

with col_left:
    st.markdown("### 🎯 ターゲット・ペルソナ設定")
    default_persona = """30歳 販売業に携わる女性
接客の仕事は好きで続けたいが、不規則な勤務シフトでの働き方を脱するためにキャリアチェンジを希望している。"""
    persona_text = st.text_area("ペルソナの詳細", value=default_persona, height=150, disabled=(st.session_state.current_step > 0))

with col_right:
    st.markdown("### 📄 評価する求人原稿")
    draft_text = st.text_area("求人原稿を入力", height=300, placeholder="ここに原稿を貼り付けます...", disabled=(st.session_state.current_step > 0))

st.markdown("<hr>", unsafe_allow_html=True)

# ── 物理的な文字数と読解時間の計算 ──
char_count = len(draft_text.replace('\n', '').replace(' ', '').replace(' ', ''))
skim_seconds = math.ceil(char_count / 15)
skim_mins, skim_secs = divmod(skim_seconds, 60)
skim_time_str = f"{skim_mins}分{skim_secs}秒" if skim_mins > 0 else f"{skim_secs}秒"
deep_seconds = math.ceil(char_count / 10)
deep_mins, deep_secs = divmod(deep_seconds, 60)
deep_time_str = f"{deep_mins}分{deep_secs}秒" if deep_mins > 0 else f"{deep_secs}秒"

CONTEXT = f"""【ターゲット・ペルソナ】\n{persona_text}\n\n【求人原稿（文字数: 約{char_count}文字）】\n{draft_text}\n\n【物理的な読解時間データ】\n・流し読み想定: {skim_time_str}\n・熟読想定: {deep_time_str}"""
SYSTEM_PROMPT = "あなたは採用マーケティングの第一人者です。ペルソナの心理に基づき、辛口かつ論理的、建設的に原稿を評価してください。冗長な前置きや挨拶は不要です。即座に本題に入ってください。"

def call_ai(prompt, step_name):
    """AIを呼び出し、結果を保存して画面に表示する共通関数"""
    try:
        client = anthropic.Anthropic(api_key=api_key)
        st.session_state.ai_messages.append({"role": "user", "content": prompt})
        
        result_placeholder = st.empty()
        full_response = ""
        
        with st.spinner(f"{step_name} を実行中..."):
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=4096, # 限界まで引き上げました
                system=SYSTEM_PROMPT,
                messages=st.session_state.ai_messages,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    result_placeholder.markdown(f'<div class="result-block">{full_response}</div>', unsafe_allow_html=True)
                    
        st.session_state.ai_messages.append({"role": "assistant", "content": full_response})
        return full_response
    except Exception as e:
        st.error(f"❌ エラーが発生しました: {e}")
        return None

# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
# STEP 1
# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
if st.session_state.current_step == 0:
    if st.button("🚀 STEP 1: 読解コストとBefore/After評価を実行"):
        if not draft_text.strip():
            st.warning("⚠️ 評価する求人原稿を入力してください。")
        else:
            prompt1 = f"""{CONTEXT}\n上記の前提を踏まえ、以下の2点について見やすいMarkdown形式で分析を出力してください。\n1. **⏱️ 読解タイム・コスト評価**: 物理的な読解時間を踏まえ、ペルソナの隙間時間に読まれる想定として適切か。離脱されないか。\n2. **🔄 Before/After の伝達度**: ペルソナの「現状の悩み」から「入社後の変化」のコントラストが鮮明に描かれているか。"""
            response = call_ai(prompt1, "STEP 1")
            if response:
                st.session_state.results[1] = response
                st.session_state.current_step = 1
                st.rerun()

if st.session_state.current_step >= 1:
    st.markdown("### 🔍 STEP 1. 読解コストとBefore/After評価")
    st.markdown(f'<div class="result-block">{st.session_state.results[1]}</div>', unsafe_allow_html=True)

# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
# STEP 2
# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
if st.session_state.current_step == 1:
    if st.button("🧠 STEP 2: 意思決定フローの採点を実行"):
        prompt2 = """見事な分析です。続けて、求人のフローが自然な心理順序に沿っているか、以下の4項目をそれぞれ【10点満点（計40点満点）】でシビアに採点し、理由と改善点を述べてください。\n① 自分事化（これは私のための求人だと思えるか）\n② 適合性の納得（シフトの悩みが解決すると確信できるか）\n③ 将来の魅力（入社後のキャリア像にワクワクするか）\n④ 応募へのハードル（今すぐ応募ボタンを押したくなるか）"""
        response = call_ai(prompt2, "STEP 2")
        if response:
            st.session_state.results[2] = response
            st.session_state.current_step = 2
            st.rerun()

if st.session_state.current_step >= 2:
    st.markdown("### 🧠 STEP 2. 意思決定フローの厳格採点")
    st.markdown(f'<div class="result-block">{st.session_state.results[2]}</div>', unsafe_allow_html=True)

# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
# STEP 3
# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
if st.session_state.current_step == 2:
    if st.button("🏆 STEP 3: 総合評価とCV期待度の算出を実行"):
        prompt3 = """ありがとうございます。次に、これまでの分析を総括し、以下の項目を出力してください。\n**🏆 総合評価**: 目標である「ペルソナ層からの応募 月5件以上」を見込めるか、総合的な「CV期待度スコア（100点満点）」を提示し、現状の課題に関する結論を論理的に述べてください。※具体的な改善コピーの作成は次のステップで行うので、ここでは課題の総括にとどめてください。"""
        response = call_ai(prompt3, "STEP 3")
        if response:
            st.session_state.results[3] = response
            st.session_state.current_step = 3
            st.rerun()

if st.session_state.current_step >= 3:
    st.markdown("### 🏆 STEP 3. 総合評価とCV期待度")
    st.markdown(f'<div class="result-block">{st.session_state.results[3]}</div>', unsafe_allow_html=True)

# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
# STEP 4
# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
if st.session_state.current_step == 3:
    if st.button("✨ STEP 4: 具体的な改善コピー提案を生成"):
        prompt4 = """最後のステップです。これまでのすべての分析と総合評価の課題を踏まえて、最高の結果を出すための【改善コピー提案】を出力してください。\n**✨ 具体的な改善コピー提案**: 採点で減点された部分を完全に補い、最後の一押しとなる「具体的な文章案（キャッチコピーや、追加・修正すべき本文の段落）」を、そのまま元の原稿にコピペして使えるレベルで実際に作成してください。プロのコピーライターとして、魅力を最大化した実際の文章を提示してください。"""
        response = call_ai(prompt4, "STEP 4")
        if response:
            st.session_state.results[4] = response
            st.session_state.current_step = 4
            st.rerun()

if st.session_state.current_step >= 4:
    st.markdown("### ✨ STEP 4. 具体的な改善コピー提案（そのまま使える修正案）")
    st.markdown(f'<div class="result-block">{st.session_state.results[4]}</div>', unsafe_allow_html=True)
    st.success("✅ 全ての分析と改善提案が完了しました！最初からやり直す場合は、一番上の「別の原稿を評価する」ボタンを押してください。")
