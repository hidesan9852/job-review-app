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

# ── カスタムCSS（専用アプリ用に少し色味を変えて見やすく） ──────────────
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
    padding: 1.8rem 2rem; margin-top: 1.5rem; box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    line-height: 1.7;
}

.stButton > button {
    background: #3b82f6 !important; color: #ffffff !important; border: none !important;
    border-radius: 8px !important; font-weight: 600 !important; font-size: 1.05rem !important;
    padding: 0.8rem 2rem !important; width: 100% !important; transition: opacity 0.2s !important;
}
.stButton > button:hover { opacity: 0.88 !important; }
</style>
""", unsafe_allow_html=True)

# ── ヘッダー ────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <h1>📝 求人原稿 添削・スコアリングエージェント</h1>
    <p>設定したペルソナの心理・読解時間をベースに、求人原稿のコンバージョン期待度を採点します</p>
</div>
""", unsafe_allow_html=True)

# ── APIキー確認 ─────────────────────────────────────────────────
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    except:
        st.error("⚠️ Anthropic APIキーが設定されていません。")
        st.stop()

# ── 入力フォーム ────────────────────────────────────────────────
col_left, col_right = st.columns([1, 1.5], gap="large")

with col_left:
    st.markdown("### 🎯 ターゲット・ペルソナ設定")
    st.write("※必要に応じて内容を書き換えてください。")
    default_persona = """30歳 販売業に携わる女性
接客の仕事は好きで続けたいが、不規則な勤務シフトでの働き方を脱するためにキャリアチェンジを希望している。"""
    persona_text = st.text_area("ペルソナの詳細", value=default_persona, height=150)

with col_right:
    st.markdown("### 📄 評価する求人原稿")
    st.write("※作成した求人原稿（タイトル＋本文）を貼り付けてください。")
    draft_text = st.text_area("求人原稿を入力", height=300, placeholder="ここに原稿を貼り付けます...")

# ── 評価実行ボタン ───────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
btn_col, _ = st.columns([1, 2])
with btn_col:
    evaluate_btn = st.button("✨ この原稿をペルソナ目線でスコアリングする")

# ── 評価処理ロジック ──────────────────────────────────────────────
if evaluate_btn:
    if not draft_text.strip():
        st.warning("⚠️ 評価する求人原稿を入力してください。")
    else:
        # 1. 物理的な文字数と読解時間の計算（アプリ側で正確に処理）
        char_count = len(draft_text.replace('\n', '').replace(' ', '').replace(' ', ''))
        
        # 流し読み（1秒15文字計算）
        skim_seconds = math.ceil(char_count / 15)
        skim_mins, skim_secs = divmod(skim_seconds, 60)
        skim_time_str = f"{skim_mins}分{skim_secs}秒" if skim_mins > 0 else f"{skim_secs}秒"
        
        # 熟読（1秒10文字計算）
        deep_seconds = math.ceil(char_count / 10)
        deep_mins, deep_secs = divmod(deep_seconds, 60)
        deep_time_str = f"{deep_mins}分{deep_secs}秒" if deep_mins > 0 else f"{deep_secs}秒"

        # 画面に計算結果を表示（ユーザー向け）
        st.info(f"📊 **原稿データ:** 文字数 約 {char_count} 文字 ｜ 📱 **想定読解時間:** 流し読み {skim_time_str} / 熟読 {deep_time_str}")

        # 2. AIへ渡す厳格な評価プロンプト
        EVAL_PROMPT = f"""あなたはプロフェッショナルな採用コピーライター兼、心理分析官です。
以下の【ターゲット・ペルソナ】の視点に完全に憑依し、【求人原稿】の訴求力と応募獲得ポテンシャルを厳格にスコアリングしてください。

【ターゲット・ペルソナ】
{persona_text}

【求人原稿（文字数: 約{char_count}文字）】
{draft_text}

【物理的な読解時間データ】
・スマホでの流し読み想定: {skim_time_str}
・じっくり熟読した場合の想定: {deep_time_str}

━━━━━━━━━━━━━━━━━━━━━
以下の1〜4の項目を、Markdown形式で見やすく出力してください。挨拶や前置きは不要です。

### 1. ⏱️ 読解タイム・コスト評価
物理的な読解時間（流し読み {skim_time_str} / 熟読 {deep_time_str}）を踏まえ、ペルソナの隙間時間（例：通勤中の電車内など）に読まれることを想定した際、この文章量は適切か？途中で離脱されないか？を評価してください。

### 2. 🔄 Before/After の伝達度
ペルソナの「現状の悩み（Before）」から、「入社後にどう変わるか（After）」のコントラストが原稿内で鮮明に描かれており、ペルソナの心に刺さる内容になっているかを評価・指摘してください。

### 3. 🧠 意思決定フローの採点（40点満点）
求人のフローが自然な心理順序に沿っているか、以下の4項目をそれぞれ【10点満点】で採点し、理由と改善点を述べてください。
① 自分事化（これは私のための求人だと思えるか）: 〇点
② 適合性の納得（シフトの悩みが解決すると確信できるか）: 〇点
③ 将来の魅力（入社後のキャリア像にワクワクするか）: 〇点
④ 応募へのハードル（今すぐ応募ボタンを押したくなるか）: 〇点

### 4. 🏆 総合評価と「月5件獲得」への最終アドバイス
総合的な「CV期待度スコア（100点満点）」を提示してください。
目標である「ペルソナ層からの応募 月5件以上獲得」を見込めるレベルに達しているかをジャッジし、達していない場合は「最後の一押しとなる具体的な追加コピー案」を提案してください。
"""

        with st.spinner("AIがペルソナの心理をシミュレーションし、原稿をスコアリング中..."):
            try:
                client = anthropic.Anthropic(api_key=api_key)
                result_placeholder = st.empty()
                full_response = ""

                with client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=3000,
                    system="あなたは採用マーケティングの第一人者です。ペルソナの心理に基づき、辛口かつ論理的、建設的に原稿を評価してください。",
                    messages=[
                        {"role": "user", "content": EVAL_PROMPT}
                    ],
                ) as stream:
                    for text in stream.text_stream:
                        full_response += text
                        result_placeholder.markdown(f'<div class="result-block">{full_response}</div>', unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"❌ 評価中にエラーが発生しました: {e}")

# ── フッター ────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.caption("Powered by Anthropic Claude · 求人原稿スコアリングシステム")
