import streamlit as st
import anthropic
import os
import math
import json

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

# ── バックアップ用のファイル設定 ─────────────────────────────────
# 【重要】Streamlit既知の不具合(Bad message format: SessionInfo)でセッションが
# 突然リセットされ結果が消えることがあるため、進捗をローカルファイルにも保存し自動復元する。
BACKUP_FILE = "streamlit_scoring_backup.json"

def save_backup():
    try:
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "current_step": st.session_state.current_step,
                "results": st.session_state.results,
                "ai_messages": st.session_state.ai_messages,
                "input_data": st.session_state.input_data,
                "history": st.session_state.history,
            }, f, ensure_ascii=False)
    except Exception:
        pass

def load_backup():
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def clear_backup():
    try:
        if os.path.exists(BACKUP_FILE):
            os.remove(BACKUP_FILE)
    except Exception:
        pass

def archive_current_version():
    """現在の入力内容と分析結果を改訂履歴に保存する(修正サイクルで前バージョンを失わないため)"""
    if st.session_state.results:
        st.session_state.history.append({
            "input_data": dict(st.session_state.input_data),
            "results": dict(st.session_state.results),
        })

# ── セッション状態の初期化（記憶機能） ─────────────────────────
if "current_step" not in st.session_state:
    st.session_state.current_step = 0
if "ai_messages" not in st.session_state:
    st.session_state.ai_messages = []
if "results" not in st.session_state:
    st.session_state.results = {}
if "input_data" not in st.session_state:
    st.session_state.input_data = {}
if "history" not in st.session_state:
    st.session_state.history = []

# タイムアウトやSessionInfo不具合でセッションが飛んだ場合、バックアップから自動復元する
if st.session_state.current_step == 0 and not st.session_state.results:
    _backup = load_backup()
    if _backup and _backup.get("current_step", 0) > 0:
        st.session_state.current_step = _backup.get("current_step", 0)
        st.session_state.results = _backup.get("results", {})
        st.session_state.ai_messages = _backup.get("ai_messages", [])
        st.session_state.input_data = _backup.get("input_data", {})
        st.session_state.history = _backup.get("history", [])

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
if st.button("🗑️ まったく新しい原稿を評価する（すべてクリア）"):
    st.session_state.current_step = 0
    st.session_state.ai_messages = []
    st.session_state.results = {}
    st.session_state.input_data = {}
    st.session_state.history = []
    clear_backup()
    st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

# ── 入力フォーム ────────────────────────────────────────────────
default_persona = """30歳 販売業に携わる女性\n接客の仕事は好きで続けたいが、不規則な勤務シフトでの働き方を脱するためにキャリアチェンジを希望している。"""

SYSTEM_PROMPT = "あなたは採用マーケティングとSEOの第一人者です。ペルソナの心理に基づき、辛口かつ論理的、建設的に原稿を評価してください。冗長な前置きや挨拶は不要です。即座に本題に入ってください。"

# 採点・分析タスクは「創造性」より「再現性」を優先するため、温度を低めに固定する。
# (0にしても厳密な決定論にはならないが、デフォルト値の1.0と比べて評価のブレは大きく減る)
EVAL_TEMPERATURE = 0.2

def call_ai(prompt, step_name):
    try:
        client = anthropic.Anthropic(api_key=api_key)
        st.session_state.ai_messages.append({"role": "user", "content": prompt})

        result_placeholder = st.empty()
        full_response = ""

        with st.spinner(f"{step_name} を実行中..."):
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                temperature=EVAL_TEMPERATURE,
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
# STEP 0(入力) ── フォーム化により、入力途中の全体再実行(ちらつき・SessionInfoエラーの誘因)を防止
# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
if st.session_state.current_step == 0:
    if st.session_state.history:
        st.info(f"✏️ 第{len(st.session_state.history) + 1}版を編集中です。前回の内容が反映されています。原稿を修正して再評価してください。")

    with st.form("step0_form", border=False):
        col_left, col_right = st.columns([1, 1.5], gap="large")

        with col_left:
            st.markdown("### 🎯 ターゲット・ペルソナ設定")
            persona_text = st.text_area(
                "ペルソナの詳細",
                value=st.session_state.input_data.get("persona_text", default_persona),
                height=120,
            )

            st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
            st.markdown("### 🔍 検索キーワード（任意）")
            target_keywords = st.text_input(
                "狙いたい検索キーワードを入力",
                value=st.session_state.input_data.get("target_keywords", ""),
                placeholder="例：事務, 未経験歓迎, 土日祝休み, 残業なし",
            )

            st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
            st.markdown("### 📢 掲載メディア（文字数制限）")
            _platform_options = ["Indeed", "AirWork", "その他"]
            _prev_platform = st.session_state.input_data.get("target_platform", "Indeed")
            _platform_index = _platform_options.index(_prev_platform) if _prev_platform in _platform_options else 0
            target_platform = st.selectbox(
                "改善案を適用するメディアを選択",
                _platform_options,
                index=_platform_index,
            )

            title_rule = ""
            catch_rule = ""

            if target_platform == "Indeed":
                title_rule = "30文字以内。【重要】Indeedの厳格なガイドラインである「職種名の一意性」を絶対厳守すること。タイトル内にアピール文言（例：未経験歓迎、急募など）や装飾記号（【】や★など）は一切含めず、純粋で一般的な職種名のみを記載すること。"
                catch_rule = "60文字以上〜80文字以内"
                st.caption("📌 タイトル: 30文字以内（※職種名の一意性を厳守） / キャッチ: 60〜80文字")
            elif target_platform == "AirWork":
                title_rule = "20文字以上〜30文字以内"
                catch_rule = "20文字以上〜30文字以内"
                st.caption("📌 タイトル: 20〜30文字 / キャッチ: 20〜30文字")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    title_rule = st.text_input(
                        "タイトルの文字数条件",
                        value=st.session_state.input_data.get("title_rule", "30文字以内"),
                    )
                with c2:
                    catch_rule = st.text_input(
                        "キャッチコピーの文字数条件",
                        value=st.session_state.input_data.get("catch_rule", "60文字以内"),
                    )

        with col_right:
            st.markdown("### 📄 評価する求人原稿")
            draft_text = st.text_area(
                "求人原稿を入力",
                value=st.session_state.input_data.get("draft_text", ""),
                height=220,
                placeholder="ここに原稿を貼り付けます...",
            )

            st.markdown("### 💡 作成の意図・留意点（任意）")
            draft_intent = st.text_area(
                "原稿に込めた思い、懸念点、AIに特に見てほしいポイントなど",
                value=st.session_state.input_data.get("draft_intent", ""),
                height=90,
                placeholder="例：残業が少ないことを一番の売りにしたいが、嫌味にならないか気になっている。",
            )

        st.markdown("<hr>", unsafe_allow_html=True)
        submitted_step1 = st.form_submit_button(
            "🚀 STEP 1: 読解コスト・構成・ゾーニングの評価を実行", use_container_width=True
        )

    if submitted_step1:
        if not draft_text.strip():
            st.warning("⚠️ 評価する求人原稿を入力してください。")
        else:
            # ── 物理的な文字数と読解時間の計算 ──
            char_count = len(draft_text.replace("\n", "").replace(" ", "").replace("　", ""))
            skim_seconds = math.ceil(char_count / 15)
            skim_mins, skim_secs = divmod(skim_seconds, 60)
            skim_time_str = f"{skim_mins}分{skim_secs}秒" if skim_mins > 0 else f"{skim_secs}秒"
            deep_seconds = math.ceil(char_count / 10)
            deep_mins, deep_secs = divmod(deep_seconds, 60)
            deep_time_str = f"{deep_mins}分{deep_secs}秒" if deep_mins > 0 else f"{deep_secs}秒"

            intent_section = f"\n\n【作成の意図・留意点】\n{draft_intent}" if draft_intent.strip() else ""
            keyword_section = f"\n\n【狙いたい検索キーワード】\n{target_keywords}" if target_keywords.strip() else ""

            CONTEXT = f"""【ターゲット・ペルソナ】\n{persona_text}\n\n【求人原稿（文字数: 約{char_count}文字）】\n{draft_text}{intent_section}{keyword_section}\n\n【物理的な読解時間データ】\n・流し読み想定: {skim_time_str}\n・熟読想定: {deep_time_str}"""

            prompt1 = f"""{CONTEXT}\n上記の前提を踏まえ、以下の3点について見やすいMarkdown形式で分析を出力してください。\n1. **⏱️ 読解タイム・コスト評価**: 物理的な読解時間を踏まえ、ペルソナの隙間時間に読まれる想定として適切か。\n2. **🔄 Before/After の伝達度**: ペルソナの「現状の悩み」から「入社後の変化」のコントラストが鮮明に描かれているか。（※作成の意図があれば、その成功度も評価）\n3. **🔍 SEOと感情訴求のゾーニング（サンドイッチ構造）**: 「アルゴリズム（機械）向けの言葉」と「求職者（人）向けの言葉」が混ざっていないかを評価します。「上部（SEO兼フック）」「中部（感情訴求・ストーリー）」「下部（SEO兼事務的条件）」のサンドイッチ構造で明確に棲み分けができているかを分析してください。"""

            response = call_ai(prompt1, "STEP 1")
            if response:
                st.session_state.input_data = {
                    "persona_text": persona_text,
                    "target_keywords": target_keywords,
                    "target_platform": target_platform,
                    "title_rule": title_rule,
                    "catch_rule": catch_rule,
                    "draft_text": draft_text,
                    "draft_intent": draft_intent,
                }
                st.session_state.results[1] = response
                st.session_state.current_step = 1
                save_backup()
                st.rerun()
else:
    st.markdown(f"#### 📝 第{len(st.session_state.history) + 1}版を分析中")

    # 入力済み内容を読み取り専用で振り返れるようにする
    with st.expander("📋 入力した内容を確認する", expanded=False):
        _d = st.session_state.input_data
        st.write(f"**掲載メディア**: {_d.get('target_platform', '-')}")
        if _d.get("target_keywords"):
            st.write(f"**検索キーワード**: {_d.get('target_keywords')}")
        st.write("**ペルソナ**")
        st.text(_d.get("persona_text", ""))
        st.write("**求人原稿**")
        st.text(_d.get("draft_text", ""))
        if _d.get("draft_intent"):
            st.write("**作成の意図・留意点**")
            st.text(_d.get("draft_intent"))

    # ── 改善サイクル用ボタン：原稿を修正して、この結果をもとにもう一度評価する ──
    if st.button("✏️ 原稿を修正してもう一度評価する", use_container_width=True, type="primary"):
        archive_current_version()
        st.session_state.current_step = 0
        st.session_state.results = {}
        st.session_state.ai_messages = []
        save_backup()
        st.rerun()
    st.caption("↑ 現在の入力内容を保持したまま原稿を編集し、STEP 1から再評価します（それまでの結果は下の改訂履歴に保存されます）")

    # ── 改訂履歴の表示 ──
    if st.session_state.history:
        with st.expander(f"📈 改訂履歴（過去{len(st.session_state.history)}版）", expanded=False):
            for i, v in enumerate(st.session_state.history):
                v_draft = v["input_data"].get("draft_text", "")
                v_preview = v_draft[:80] + "…" if len(v_draft) > 80 else v_draft
                st.markdown(f"**第{i + 1}版**　`{v_preview}`")
                for step_no, step_label in [(1, "STEP1 読解コスト・構成"), (2, "STEP2 意思決定フロー採点"), (3, "STEP3 総合評価"), (4, "STEP4 改善コピー")]:
                    if v["results"].get(step_no):
                        st.markdown(f"**└ {step_label}**")
                        st.markdown(f'<div class="result-block" style="padding:1rem 1.2rem; margin-top:0.3rem; margin-bottom:0.8rem;">{v["results"][step_no]}</div>', unsafe_allow_html=True)
                st.markdown("---")

    st.markdown("<hr>", unsafe_allow_html=True)

if st.session_state.current_step >= 1:
    st.markdown("### 🔍 STEP 1. 読解コスト・構成・ゾーニングの評価")
    st.markdown(f'<div class="result-block">{st.session_state.results.get(1, "")}</div>', unsafe_allow_html=True)

# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
# STEP 2
# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
if st.session_state.current_step == 1:
    if st.button("🧠 STEP 2: 意思決定フローの採点を実行"):
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
            save_backup()
            st.rerun()

if st.session_state.current_step >= 2:
    st.markdown("### 🧠 STEP 2. 意思決定フローの厳格採点")
    st.markdown(f'<div class="result-block">{st.session_state.results.get(2, "")}</div>', unsafe_allow_html=True)

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
            save_backup()
            st.rerun()

if st.session_state.current_step >= 3:
    st.markdown("### 🏆 STEP 3. 総合評価とCV期待度")
    st.markdown(f'<div class="result-block">{st.session_state.results.get(3, "")}</div>', unsafe_allow_html=True)

# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
# STEP 4
# ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
if st.session_state.current_step == 3:
    if st.button("✨ STEP 4: 具体的な改善コピー提案を生成"):
        _d = st.session_state.input_data
        target_platform = _d.get("target_platform", "")
        title_rule = _d.get("title_rule", "")
        catch_rule = _d.get("catch_rule", "")
        prompt4 = f"""最後のステップです。これまでのすべての分析と総合評価の課題を踏まえて、最高の結果を出すための【改善コピー提案】を出力してください。

【適用する厳格なルール（掲載媒体: {target_platform}）】
・求人タイトルのルール: {title_rule}
・キャッチコピーのルール: {catch_rule}
※上記のルールは絶対厳守してください。媒体ポリシーの違反は致命的なエラーとなります。

**✨ 具体的な改善コピー提案**: 
作成者の意図を汲み取りつつ、採点で減点された部分を補い、そのまま元の原稿にコピペして使えるレベルの「具体的な文章案」を提示してください。
必ず、以下の【サンドイッチ構造】で原稿を再構築してください。
1. **上部（SEO兼フックゾーン）**: 検索キーワードを箇条書きや短い文章で配置し、アルゴリズムと初期クリックを稼ぐ。
2. **中部（感情訴求・ストーリーゾーン）**: SEOから完全に切り離し、人の心を動かす心地よい自然な言葉で、ペルソナの悩みをどう解決するかを書き切る。
3. **下部（SEO兼事務的条件ゾーン）**: 求める人材や福利厚生など、アルゴリズムに対するキーワードの網羅性を担保する。

見出しには検索キーワードを組み込み、感情は検索キーワードに翻訳（言い換え）して配置すること。プロのコピーライターとして、魅力を最大化した実際の文章を提示してください。"""
        response = call_ai(prompt4, "STEP 4")
        if response:
            st.session_state.results[4] = response
            st.session_state.current_step = 4
            save_backup()
            st.rerun()

if st.session_state.current_step >= 4:
    st.markdown("### ✨ STEP 4. 具体的な改善コピー提案（そのまま使える修正案）")
    st.markdown(f'<div class="result-block">{st.session_state.results.get(4, "")}</div>', unsafe_allow_html=True)
    st.success("✅ 全ての分析と改善提案が完了しました！この内容で原稿を直してすぐ再評価したい場合は上の「✏️ 原稿を修正してもう一度評価する」を、まったく別の原稿を評価する場合は一番上の「🗑️ まったく新しい原稿を評価する」を押してください。")
