import streamlit as st
import math
from common import render_header, call_ai, build_combined_draft

render_header("🔍 読解コスト・構成評価", "STEP1: 読解コスト・構成・ゾーニングの評価 → STEP2: 意思決定フローの採点")

if not st.session_state.input_data:
    st.warning("⚠️ まずは「📝 原稿入力」ページで原稿を入力・保存してから、このページに進んでください。")
    st.stop()

_d = st.session_state.input_data

with st.expander("📋 入力した内容を確認する", expanded=False):
    st.write(f"**掲載メディア**: {_d.get('target_platform', '-')}")
    if _d.get("target_keywords"):
        st.write(f"**検索キーワード**: {_d.get('target_keywords')}")
    st.write("**ペルソナ**")
    st.text(_d.get("persona_text", ""))
    st.write("**求人原稿**")
    st.text(build_combined_draft(_d)[:2000])

st.markdown("<hr>", unsafe_allow_html=True)

# ── STEP1: 読解コスト・構成・ゾーニングの評価 ─────────────────────
if st.session_state.current_step == 0:
    if st.button("🚀 STEP 1: 読解コスト・構成・ゾーニングの評価を実行", use_container_width=True):
        combined_draft = build_combined_draft(_d)
        target_platform = _d.get("target_platform", "")

        char_count = len(combined_draft.replace("\n", "").replace(" ", "").replace("　", ""))
        skim_seconds = math.ceil(char_count / 15)
        skim_mins, skim_secs = divmod(skim_seconds, 60)
        skim_time_str = f"{skim_mins}分{skim_secs}秒" if skim_mins > 0 else f"{skim_secs}秒"
        deep_seconds = math.ceil(char_count / 10)
        deep_mins, deep_secs = divmod(deep_seconds, 60)
        deep_time_str = f"{deep_mins}分{deep_secs}秒" if deep_mins > 0 else f"{deep_secs}秒"

        draft_intent = _d.get("draft_intent", "")
        target_keywords = _d.get("target_keywords", "")
        intent_section = f"\n\n【作成の意図・留意点】\n{draft_intent}" if draft_intent.strip() else ""
        keyword_section = f"\n\n【狙いたい検索キーワード】\n{target_keywords}" if target_keywords.strip() else ""

        CONTEXT = f"""【ターゲット・ペルソナ】\n{_d.get('persona_text', '')}\n\n【求人原稿（文字数: 約{char_count}文字）】\n{combined_draft}{intent_section}{keyword_section}\n\n【物理的な読解時間データ】\n・流し読み想定: {skim_time_str}\n・熟読想定: {deep_time_str}"""

        if target_platform == "AirWork":
            zoning_point = """3. **🔍 SEOと感情訴求のゾーニング**: AirWorkは項目ごとに入力欄が分かれています。「求人タイトル」「キャッチコピー」など検索・クリック獲得に直結する項目に効果的なキーワードが含まれているか、「お仕事について」「求める人材」などの本文で、アルゴリズム向けの機械的な言葉と求職者の心に響く感情的な言葉が適切に使い分けられているかを、項目ごとに具体的に指摘してください。"""
        elif target_platform == "Indeed":
            zoning_point = """3. **🔍 SEOと感情訴求のゾーニング**: Indeedは項目ごとに入力欄が分かれています。「求人タイトル」「キャッチコピー」など検索結果・クリック獲得に直結する項目に効果的なキーワードが含まれているか、「仕事内容」「求める人材」「アピールポイント」などの本文で、アルゴリズム向けの機械的な言葉と求職者の心に響く感情的な言葉が適切に使い分けられているかを、項目ごとに具体的に指摘してください。"""
        else:
            zoning_point = """3. **🔍 SEOと感情訴求のゾーニング（サンドイッチ構造）**: 「アルゴリズム（機械）向けの言葉」と「求職者（人）向けの言葉」が混ざっていないかを評価します。「上部（SEO兼フック）」「中部（感情訴求・ストーリー）」「下部（SEO兼事務的条件）」のサンドイッチ構造で明確に棲み分けができているかを分析してください。"""

        prompt1 = f"""{CONTEXT}\n上記の前提を踏まえ、以下の3点について見やすいMarkdown形式で分析を出力してください。\n1. **⏱️ 読解タイム・コスト評価**: 物理的な読解時間を踏まえ、ペルソナの隙間時間に読まれる想定として適切か。\n2. **🔄 Before/After の伝達度**: ペルソナの「現状の悩み」から「入社後の変化」のコントラストが鮮明に描かれているか。（※作成の意図があれば、その成功度も評価）ただし、コントラストを鮮明にするために前職への批判や、過度にネガティブ・不安を煽る表現（例:「放任されていた」「社会保険にも入っていない」等を強調する言い回し）を使っている場合は、それは高評価ではなく、誠実さを欠く表現として明確に指摘してください。\n{zoning_point}"""

        response = call_ai(prompt1, "STEP 1")
        if response:
            st.session_state.results[1] = response
            st.session_state.current_step = 1
            st.rerun()

if st.session_state.current_step >= 1:
    st.markdown("### 🔍 STEP 1. 読解コスト・構成・ゾーニングの評価")
    st.markdown(f'<div class="result-block">{st.session_state.results.get(1, "")}</div>', unsafe_allow_html=True)

# ── STEP2: 意思決定フローの採点 ───────────────────────────────
if st.session_state.current_step == 1:
    if st.button("🧠 STEP 2: 意思決定フローの採点を実行", use_container_width=True):
        prompt2 = """見事な分析です。続けて、求人のフローが自然な心理順序に沿っているか、以下の4項目をそれぞれ【10点満点（計40点満点）】でシビアに採点し、理由と改善点を述べてください。
その際、「見出しはSEO、本文は感情」という構成になっているか、また、感情訴求が単なるポエムにならず、ペルソナの感情が「検索キーワード」に正しく翻訳（言い換え）されて原稿に組み込まれているかも加味してください。
① 自分事化（これは私のための求人だと思えるか）
② 適合性の納得（シフトの悩みが解決すると確信できるか）
③ 将来の魅力（入社後のキャリア像にワクワクするか）
④ 応募へのハードル（今すぐ応募ボタンを押したくなるか）"""
        response = call_ai(prompt2, "STEP 2")
        if response:
            st.session_state.results[2] = response
            st.session_state.current_step = 2
            st.rerun()

if st.session_state.current_step >= 2:
    st.markdown("### 🧠 STEP 2. 意思決定フローの厳格採点")
    st.markdown(f'<div class="result-block">{st.session_state.results.get(2, "")}</div>', unsafe_allow_html=True)
    st.success("✅ STEP1・STEP2が完了しました。左のナビゲーションから「✨ 総合評価・改善コピー」に進んでください。")
