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
</style>
""", unsafe_allow_html=True)

# ── ヘッダー ────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <h1>📝 求人原稿 添削・スコアリングエージェント</h1>
    <p>設定したペルソナの心理・読解時間をベースに、3段階の深い分析と改善提案を行います</p>
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
    evaluate_btn = st.button("✨ 段階的スコアリングを実行する")

# ── 評価処理ロジック（3段階連鎖） ──────────────────────────────────
if evaluate_btn:
    if not draft_text.strip():
        st.warning("⚠️ 評価する求人原稿を入力してください。")
    else:
        # 1. 物理的な文字数と読解時間の計算
        char_count = len(draft_text.replace('\n', '').replace(' ', '').replace(' ', ''))
        
        skim_seconds = math.ceil(char_count / 15)
        skim_mins, skim_secs = divmod(skim_seconds, 60)
        skim_time_str = f"{skim_mins}分{skim_secs}秒" if skim_mins > 0 else f"{skim_secs}秒"
        
        deep_seconds = math.ceil(char_count / 10)
        deep_mins, deep_secs = divmod(deep_seconds, 60)
        deep_time_str = f"{deep_mins}分{deep_secs}秒" if deep_mins > 0 else f"{deep_secs}秒"

        st.info(f"📊 **原稿データ:** 文字数 約 {char_count} 文字 ｜ 📱 **想定読解時間:** 流し読み {skim_time_str} / 熟読 {deep_time_str}")

        try:
            client = anthropic.Anthropic(api_key=api_key)
            SYSTEM_PROMPT = "あなたは採用マーケティングの第一人者です。ペルソナの心理に基づき、辛口かつ論理的、建設的に原稿を評価してください。冗長な前置きや挨拶は不要です。即座に本題に入ってください。"
            
            # AIに渡す共通の前提情報
            CONTEXT = f"""【ターゲット・ペルソナ】\n{persona_text}\n\n【求人原稿（文字数: 約{char_count}文字）】\n{draft_text}\n\n【物理的な読解時間データ】\n・流し読み想定: {skim_time_str}\n・熟読想定: {deep_time_str}"""

            # 会話の記憶を保存するリスト
            messages_history = []
            
            # ＝＝＝ 段階1：読解コストとBefore/After評価 ＝＝＝
            st.markdown("### 🔍 STEP 1. 読解コストとBefore/After評価")
            result_placeholder_1 = st.empty()
            full_response_1 = ""
            
            prompt1 = f"""{CONTEXT}
上記の前提を踏まえ、まずは以下の2点について見やすいMarkdown形式で分析を出力してください。
1. **⏱️ 読解タイム・コスト評価**: 物理的な読解時間を踏まえ、ペルソナの隙間時間に読まれる想定として適切か。離脱されないか。
2. **🔄 Before/After の伝達度**: ペルソナの「現状の悩み」から「入社後の変化」のコントラストが鮮明に描かれているか。"""
            
            messages_history.append({"role": "user", "content": prompt1})
            
            with st.spinner("STEP 1: 読解コストと構成を分析中..."):
                with client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=2000,
                    system=SYSTEM_PROMPT,
                    messages=messages_history,
                ) as stream:
                    for text in stream.text_stream:
                        full_response_1 += text
                        result_placeholder_1.markdown(f'<div class="result-block">{full_response_1}</div>', unsafe_allow_html=True)
            
            # AIの回答を記憶に追加
            messages_history.append({"role": "assistant", "content": full_response_1})
            
            # ＝＝＝ 段階2：意思決定フローの採点 ＝＝＝
            st.markdown("### 🧠 STEP 2. 意思決定フローの厳格採点")
            result_placeholder_2 = st.empty()
            full_response_2 = ""
            
            prompt2 = """見事な分析です。続けて、求人のフローが自然な心理順序に沿っているか、以下の4項目をそれぞれ【10点満点（計40点満点）】でシビアに採点し、理由と改善点を述べてください。
① 自分事化（これは私のための求人だと思えるか）
② 適合性の納得（シフトの悩みが解決すると確信できるか）
③ 将来の魅力（入社後のキャリア像にワクワクするか）
④ 応募へのハードル（今すぐ応募ボタンを押したくなるか）"""
            
            messages_history.append({"role": "user", "content": prompt2})
            
            with st.spinner("STEP 2: 心理的な意思決定フローを採点中..."):
                with client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=2000,
                    system=SYSTEM_PROMPT,
                    messages=messages_history,
                ) as stream:
                    for text in stream.text_stream:
                        full_response_2 += text
                        result_placeholder_2.markdown(f'<div class="result-block">{full_response_2}</div>', unsafe_allow_html=True)
                        
            # AIの回答を記憶に追加
            messages_history.append({"role": "assistant", "content": full_response_2})
            
            # ＝＝＝ 段階3：総合評価と具体的な改善提案 ＝＝＝
            st.markdown("### 🏆 STEP 3. 総合評価と【改善コピー提案】")
            result_placeholder_3 = st.empty()
            full_response_3 = ""
            
            prompt3 = """ありがとうございます。最後に、これまでの分析を総括し、以下の2点を出力してください。
1. **🏆 総合評価**: 目標である「ペルソナ層からの応募 月5件以上」を見込めるか、総合的な「CV期待度スコア（100点満点）」を提示し、結論を述べてください。
2. **✨ 具体的な改善コピー提案（そのまま使える修正案）**: 採点で減点された部分を補い、最後の一押しとなる「具体的な文章案（キャッチコピーや、追加すべき本文の段落）」を、そのまま元の原稿にコピペして使えるレベルで実際に作成してください。抽象的なアドバイスではなく、プロのコピーライターとして実際に原稿を書いてください。"""
            
            messages_history.append({"role": "user", "content": prompt3})
            
            with st.spinner("STEP 3: 総合評価と具体的な改善案を生成中..."):
                with client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=2500,
                    system=SYSTEM_PROMPT,
                    messages=messages_history,
                ) as stream:
                    for text in stream.text_stream:
                        full_response_3 += text
                        result_placeholder_3.markdown(f'<div class="result-block">{full_response_3}</div>', unsafe_allow_html=True)

            st.success("✅ 全ての分析と改善提案が完了しました！")
            
        except Exception as e:
            st.error(f"❌ 評価中にエラーが発生しました: {e}")

# ── フッター ────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.caption("Powered by Anthropic Claude · 求人原稿スコアリングシステム")
