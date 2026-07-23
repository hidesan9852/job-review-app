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

# タイムアウトやSessionInfo不具合でセッションが飛んだ場合、バックアップから自動復元する。
# 【重要】current_stepが完全に進んでいる場合だけでなく、生成途中のチェックポイント
# (current_stepはまだ0/前のままだが、resultsに部分的な内容が保存されている状態)も
# 復元対象にする。そうしないと、STEP完了直前で接続が切れた際の保存が無意味になる。
if st.session_state.current_step == 0 and not st.session_state.results:
    _backup = load_backup()
    if _backup and (_backup.get("current_step", 0) > 0 or _backup.get("results") or _backup.get("input_data")):
        st.session_state.current_step = _backup.get("current_step", 0)
        # 【重要】JSON保存時にdictのキーは必ず文字列化される(例: 1 → "1")。
        # このアプリはresultsのキーとして整数(1〜4)を使っているため、復元時に
        # 文字列キーのままだと st.session_state.results.get(1, "") 等が常にヒットせず
        # 「結果が空欄のまま」という、エラーにもならない不具合につながる。整数に戻す。
        _restored_results = _backup.get("results", {})
        st.session_state.results = {int(k): v for k, v in _restored_results.items()}
        st.session_state.ai_messages = _backup.get("ai_messages", [])
        st.session_state.input_data = _backup.get("input_data", {})
        # 改訂履歴の各版が持つresultsも同じ理由でキーを整数に戻す
        _restored_history = _backup.get("history", [])
        for _v in _restored_history:
            if isinstance(_v.get("results"), dict):
                _v["results"] = {int(k): val for k, val in _v["results"].items()}
        st.session_state.history = _restored_history

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

SYSTEM_PROMPT = "あなたは採用マーケティングとSEOの第一人者です。ペルソナの心理に基づき、辛口かつ論理的、建設的に原稿を評価してください。冗長な前置きや挨拶は不要です。即座に本題に入ってください。ペルソナの潜在的なニーズや不安に訴えることは重要ですが、それを理由に前職への批判や『放任されていた』『社会保険にも入っていない』のような、過度にネガティブで不安を煽る表現を評価文中や改善提案で使うことは避けてください。ネガティブな感情を煽って引き寄せるのではなく、誠実でポジティブな言葉で潜在ニーズに応える表現を一貫して用いてください。"

# ── AirWork入力項目の定義 ──────────────────────────────────────
# 【重要】この順序はAirWorkのUI仕様として固定されているものとして扱う。
# 求人タイトル・キャッチコピーは特殊処理(文字数上限30・タイトルは雇用形態の自動プレフィックスあり)のため別扱いとし、
# それ以外の11項目をここに定義する。(キー, ラベル, 文字数上限 or None, テキストエリアの高さ)
EMPLOYMENT_TYPES = ["正社員", "契約社員", "アルバイト・パート"]

AIRWORK_FIELDS = [
    ("job_content",      "お仕事について",       4000, 200),
    ("candidate",        "求める人材",           4000, 200),
    ("location",         "勤務地",               None, 68),
    ("salary",           "給与",                 1000, 120),
    ("work_hours",       "勤務時間",             3800, 180),
    ("holidays",         "休日休暇",             1000, 100),
    ("benefits",         "社会保険/福利厚生",    4000, 180),
    ("workplace",        "職場環境",             128,  80),
    ("trial_period",     "試用・研修期間",       250,  80),
    ("application_flow", "応募とその後の流れ",   1000, 120),
    ("company_info",     "会社情報",             None, 120),
]

def build_full_airwork_title(af, employment_type):
    """AirWorkの仕様で自動付与される雇用形態プレフィックスを含む、実際に表示される求人タイトルを組み立てる"""
    return f"【{employment_type}】{af.get('title', '')}"

def validate_airwork_fields(af, employment_type):
    """AirWorkの各項目が文字数上限を超えていないかチェックする。超過している項目のリストを返す"""
    errors = []
    title_text = af.get("title", "")
    if len(title_text) > 30:
        errors.append(f"求人タイトル: {len(title_text)}文字（上限30文字。「【{employment_type}】」の自動付与部分は含みません）")
    if len(af.get("catch", "")) > 30:
        errors.append(f"キャッチコピー: {len(af.get('catch', ''))}文字（上限30文字）")
    for key, label, limit, _ in AIRWORK_FIELDS:
        if limit and len(af.get(key, "")) > limit:
            errors.append(f"{label}: {len(af.get(key, ''))}文字（上限{limit}文字）")
    return errors

def build_airwork_draft_text(af, employment_type):
    """AirWorkの各入力欄を、AIが読める1つの原稿テキスト(項目名・文字数付き)に組み立てる"""
    full_title = build_full_airwork_title(af, employment_type)
    title_text = af.get("title", "")
    parts = [
        f"■求人タイトル（実際にはAirWorkの仕様で雇用形態「【{employment_type}】」が自動で先頭に付与された下記の形で表示される。文字数上限30文字はこのプレフィックスを含まない自由入力部分のみに適用/自由入力部分は現在{len(title_text)}文字）\n{full_title}",
        f"■キャッチコピー（上限30文字/現在{len(af.get('catch', ''))}文字）\n{af.get('catch', '')}",
    ]
    for key, label, limit, _ in AIRWORK_FIELDS:
        val = af.get(key, "")
        limit_str = f"上限{limit}文字/現在{len(val)}文字" if limit else f"現在{len(val)}文字"
        parts.append(f"■{label}（{limit_str}）\n{val}")
    return "\n\n".join(parts)

def get_draft_preview(input_data, max_len=80):
    """改訂履歴のプレビュー用に、原稿の一部を取り出す(自由記述/AirWork/Indeed構造化の3対応)"""
    if input_data.get("airwork_fields"):
        text = input_data["airwork_fields"].get("job_content", "") or input_data["airwork_fields"].get("title", "")
    elif input_data.get("indeed_fields"):
        text = input_data["indeed_fields"].get("job_content", "") or input_data["indeed_fields"].get("title", "")
    else:
        text = input_data.get("draft_text", "")
    return text[:max_len] + "…" if len(text) > max_len else text

# ── Indeed入力項目の定義 ───────────────────────────────────────
# 【重要】この順序はIndeedのUI仕様として固定されているものとして扱う。
# 求人タイトル(上限30文字)・キャッチコピー(上限80文字)は他項目と別扱いとし、
# それ以外の18項目をここに定義する。(キー, ラベル, 文字数上限 or None, テキストエリアの高さ)
INDEED_FIELDS = [
    ("job_content",         "仕事内容",           None, 200),
    ("candidate",           "求める人材",         None, 150),
    ("appeal_points",       "アピールポイント",   None, 150),
    ("work_days",           "勤務地・曜日",       None, 80),
    ("work_style",          "勤務形態",           None, 68),
    ("holidays",            "休暇休日",           None, 100),
    ("work_location",       "勤務地所在地",       None, 68),
    ("work_location_note",  "勤務地備考",         None, 80),
    ("access",              "アクセス",           None, 80),
    ("salary",              "給与",               None, 120),
    ("trial_period",        "試用期間",           None, 80),
    ("benefits",            "待遇福利厚生",       None, 150),
    ("social_insurance",    "社会保険",           None, 100),
    ("company_name",        "企業名",             None, 68),
    ("hq_location",         "本社所在地",         None, 68),
    ("industry",            "業種",               None, 68),
    ("representative",      "代表者",             None, 68),
    ("others",              "その他",             None, 100),
]

def validate_indeed_fields(inf):
    """Indeedの各項目が文字数上限を超えていないかチェックする。超過している項目のリストを返す"""
    errors = []
    if len(inf.get("title", "")) > 30:
        errors.append(f"求人タイトル: {len(inf.get('title', ''))}文字（上限30文字）")
    if len(inf.get("catch", "")) > 80:
        errors.append(f"キャッチコピー: {len(inf.get('catch', ''))}文字（上限80文字）")
    for key, label, limit, _ in INDEED_FIELDS:
        if limit and len(inf.get(key, "")) > limit:
            errors.append(f"{label}: {len(inf.get(key, ''))}文字（上限{limit}文字）")
    return errors

def build_indeed_draft_text(inf):
    """Indeedの各入力欄を、AIが読める1つの原稿テキスト(項目名・文字数付き)に組み立てる"""
    parts = [
        f"■求人タイトル（上限30文字/現在{len(inf.get('title', ''))}文字）\n{inf.get('title', '')}",
        f"■キャッチコピー（上限80文字/現在{len(inf.get('catch', ''))}文字）\n{inf.get('catch', '')}",
    ]
    for key, label, limit, _ in INDEED_FIELDS:
        val = inf.get(key, "")
        limit_str = f"上限{limit}文字/現在{len(val)}文字" if limit else f"現在{len(val)}文字"
        parts.append(f"■{label}（{limit_str}）\n{val}")
    return "\n\n".join(parts)

# 採点・分析タスクは「創造性」より「再現性」を優先するため、温度を低めに固定する。
# (0にしても厳密な決定論にはならないが、デフォルト値の1.0と比べて評価のブレは大きく減る)
EVAL_TEMPERATURE = 0.2

def call_ai(prompt, step_name, step_number=None):
    try:
        client = anthropic.Anthropic(api_key=api_key)
        st.session_state.ai_messages.append({"role": "user", "content": prompt})

        full_response = ""

        with st.spinner(f"{step_name} を実行中...（画面は動きませんが処理は進んでいます）"):
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=16384,
                temperature=EVAL_TEMPERATURE,
                system=SYSTEM_PROMPT,
                messages=st.session_state.ai_messages,
            ) as stream:
                _chunk = 0
                for text in stream.text_stream:
                    full_response += text
                    _chunk += 1
                    # 【重要】生成中は画面を一切更新しない。1文字ずつ描画すると、その回数分の
                    # WebSocket通信が発生し「Bad message format」を誘発しやすくなるため、
                    # 生成完了後に一度だけ描画する（下のresult_placeholderで実施）。
                    # 生成途中で接続が切れても被害を最小限にするため、定期的に途中経過だけは保存しておく
                    if step_number is not None and _chunk % 40 == 0:
                        st.session_state.results[step_number] = full_response
                        save_backup()

        result_placeholder = st.empty()
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

    # 【重要】掲載メディアの選択は、以下の入力欄の表示形式(AirWork用13項目 or 自由記述)を
    # その場で切り替える必要があるため、あえてフォームの外に置く。
    # フォーム内のウィジェットは送信するまで他の表示に反映されない(Streamlitの仕様)ため。
    st.markdown("### 📢 掲載メディア（文字数制限）")
    _platform_options = ["Indeed", "AirWork", "その他"]
    _prev_platform = st.session_state.input_data.get("target_platform", "Indeed")
    _platform_index = _platform_options.index(_prev_platform) if _prev_platform in _platform_options else 0
    target_platform = st.selectbox(
        "改善案を適用するメディアを選択",
        _platform_options,
        index=_platform_index,
    )
    if target_platform == "Indeed":
        st.caption("📌 求人タイトル: 30文字以内（※職種名の一意性を厳守） / キャッチコピー: 80文字以内 / その他18項目は下記フォームで個別に入力")
    elif target_platform == "AirWork":
        st.caption("📌 求人タイトル: 自由入力部分30文字以内（雇用形態の自動付与部分は別途） / キャッチコピー: 30文字以内 / その他11項目は下記フォームで個別に入力")

    with st.form("step0_form", border=False):
        col_left, col_right = st.columns([1, 1.5], gap="large")

        with col_left:
            st.markdown("### 🎯 ターゲット・ペルソナ設定")
            persona_text = st.text_area(
                "ペルソナの詳細",
                value=st.session_state.input_data.get("persona_text", ""),
                height=120,
                placeholder=default_persona,
            )

            st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
            st.markdown("### 🔍 検索キーワード（任意）")
            target_keywords = st.text_input(
                "狙いたい検索キーワードを入力",
                value=st.session_state.input_data.get("target_keywords", ""),
                placeholder="例：事務, 未経験歓迎, 土日祝休み, 残業なし",
            )

            title_rule = ""
            catch_rule = ""

            if target_platform == "Indeed":
                title_rule = """30文字以内。Indeedの実際のガイドラインに基づき、以下を厳守すること。

【✅ 記載してよい・むしろ推奨されること】
仕事内容そのものを具体化する情報は、アピール文言ではなく「求人の質」を上げる要素としてIndeedに評価される。
・取り扱う商品/サービスの種類（例:「営業」→「不動産投資の反響営業」）
・対象とする顧客/施設の種類（例:「設計技術者」→「医療機器の設計技術者」）
・専門分野や必須資格名（例:「介護職」→「生活相談員（社会福祉士）」）
・勤務先の業態を括弧書きで補足し、コア業務（職種）を先頭に置く（例:「キッチンスタッフ（保育園）」）。
  ※これは装飾ではなく、Indeed側のカテゴリ分類・検索マッチング精度を上げるための実務的なテクニック。
  ※逆に「保育園のキッチンスタッフ」のように施設名を先頭にすると、Indeedが誤ったカテゴリ（保育士カテゴリ等）に分類し、本来ターゲットにしたい求職者（調理職を探している人）に届きにくくなる。必ずコア業務を先頭に置くこと。
  ※【重要】括弧内で補足してよいのは、原則として1つの明確な要素（施設タイプ・商材・対象顧客のいずれか1つ）に絞ること。カンマ区切りで複数の要素を列挙すると、内容の説明ではなく検索キーワードの羅列とみなされるリスクが上がる。複数の事業領域を扱っている場合は、最も特徴的・差別化になる1つだけを選んで記載すること。これは明確な減点対象として指摘すること（「グレーゾーン」ではなく具体的な修正指示として扱う）。

【❌ 記載してはいけないこと（Indeedが明確に禁止）】
・候補者の条件・歓迎要素（例:「未経験歓迎」「経験者歓迎」「経験不問」）
・待遇・勤務条件に関するアピール（例:「高時給」「短時間勤務」「オープニングスタッフ」「急募」）
・記号による装飾（例:「！」「♪」「★」「【】」などの強調記号）
・1求人に複数の職種名を並記すること（1求人＝1職種が原則）

これらを踏まえ、単に「シンプルすぎる」「情報が薄い」と評するだけでなく上記【✅】に該当する具体的な追加要素を提案し、単に「ガイドライン違反」と切り捨てるだけでなく上記【❌】のどの項目に該当するかを名指しで指摘すること。
【重要】判定は上記の【✅】【❌】の基準のみに基づいて行うこと。ここに明記されていない、より厳格な独自基準（「職種名・勤務形態・資格以外は一切不可」等）を持ち出して減点しないこと。上記に該当しない限り、業務内容の具体化は加点要素として扱うこと。"""
                catch_rule = "80文字以内"
            elif target_platform == "AirWork":
                title_rule = "自由入力部分30文字以内（雇用形態の自動付与部分は含まない）"
                catch_rule = "30文字以内"
            else:
                st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
                st.markdown("### ✏️ 文字数条件（カスタム）")
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
            if target_platform == "AirWork":
                st.markdown("### 📄 評価する求人原稿（AirWork入力項目）")
                st.caption("AirWorkの入力欄の並び・上限文字数に合わせています。項目ごとに入力してください。")

                _af = st.session_state.input_data.get("airwork_fields", {})
                _prev_emp = st.session_state.input_data.get("employment_type", "正社員")
                _emp_index = EMPLOYMENT_TYPES.index(_prev_emp) if _prev_emp in EMPLOYMENT_TYPES else 0

                employment_type = st.selectbox(
                    "雇用形態（求人タイトルの先頭に自動で付与されます・変更不可の仕様）",
                    EMPLOYMENT_TYPES,
                    index=_emp_index,
                )
                st.caption(f"📌 求人タイトルは実際には「【{employment_type}】+ 以下の入力内容」の形で表示されます（この自動付与はAirWork側の仕様であり変更できません）")

                airwork_values = {}
                airwork_values["title"] = st.text_input(
                    f"求人タイトル（上限30文字。「【{employment_type}】」の自動付与部分は含みません）",
                    value=_af.get("title", ""),
                )
                airwork_values["catch"] = st.text_input(
                    "キャッチコピー（上限30文字）",
                    value=_af.get("catch", ""),
                )
                for key, label, limit, height in AIRWORK_FIELDS:
                    label_with_limit = f"{label}（上限{limit}文字）" if limit else label
                    airwork_values[key] = st.text_area(
                        label_with_limit,
                        value=_af.get(key, ""),
                        height=height,
                    )

                st.markdown("### 💡 作成の意図・留意点（任意）")
                draft_intent = st.text_area(
                    "原稿に込めた思い、懸念点、AIに特に見てほしいポイントなど",
                    value=st.session_state.input_data.get("draft_intent", ""),
                    height=90,
                    placeholder="例：残業が少ないことを一番の売りにしたいが、嫌味にならないか気になっている。",
                )
            elif target_platform == "Indeed":
                st.markdown("### 📄 評価する求人原稿（Indeed入力項目）")
                st.caption("Indeedの入力欄の並びに合わせています。項目ごとに入力してください。")

                _inf = st.session_state.input_data.get("indeed_fields", {})

                indeed_values = {}
                indeed_values["title"] = st.text_input(
                    "求人タイトル（上限30文字）",
                    value=_inf.get("title", ""),
                )
                indeed_values["catch"] = st.text_input(
                    "キャッチコピー（上限80文字）",
                    value=_inf.get("catch", ""),
                )
                for key, label, limit, height in INDEED_FIELDS:
                    label_with_limit = f"{label}（上限{limit}文字）" if limit else label
                    indeed_values[key] = st.text_area(
                        label_with_limit,
                        value=_inf.get(key, ""),
                        height=height,
                    )

                st.markdown("### 💡 作成の意図・留意点（任意）")
                draft_intent = st.text_area(
                    "原稿に込めた思い、懸念点、AIに特に見てほしいポイントなど",
                    value=st.session_state.input_data.get("draft_intent", ""),
                    height=90,
                    placeholder="例：残業が少ないことを一番の売りにしたいが、嫌味にならないか気になっている。",
                )
            else:
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
        if target_platform == "AirWork":
            validation_errors = validate_airwork_fields(airwork_values, employment_type)
            combined_draft = build_airwork_draft_text(airwork_values, employment_type)
            is_empty = not any(v.strip() for v in airwork_values.values())
        elif target_platform == "Indeed":
            validation_errors = validate_indeed_fields(indeed_values)
            combined_draft = build_indeed_draft_text(indeed_values)
            is_empty = not any(v.strip() for v in indeed_values.values())
        else:
            validation_errors = []
            combined_draft = draft_text
            is_empty = not draft_text.strip()

        if is_empty:
            st.warning("⚠️ 評価する求人原稿を入力してください。")
        elif not persona_text.strip():
            st.warning("⚠️ ターゲット・ペルソナの詳細を入力してください。")
        elif validation_errors:
            st.error(
                "⚠️ 以下の項目が文字数の上限を超えています。修正のうえ、再度実行してください。\n\n"
                + "\n".join(f"- {e}" for e in validation_errors)
            )
        else:
            # ── 物理的な文字数と読解時間の計算 ──
            char_count = len(combined_draft.replace("\n", "").replace(" ", "").replace("　", ""))
            skim_seconds = math.ceil(char_count / 15)
            skim_mins, skim_secs = divmod(skim_seconds, 60)
            skim_time_str = f"{skim_mins}分{skim_secs}秒" if skim_mins > 0 else f"{skim_secs}秒"
            deep_seconds = math.ceil(char_count / 10)
            deep_mins, deep_secs = divmod(deep_seconds, 60)
            deep_time_str = f"{deep_mins}分{deep_secs}秒" if deep_mins > 0 else f"{deep_secs}秒"

            intent_section = f"\n\n【作成の意図・留意点】\n{draft_intent}" if draft_intent.strip() else ""
            keyword_section = f"\n\n【狙いたい検索キーワード】\n{target_keywords}" if target_keywords.strip() else ""

            CONTEXT = f"""【ターゲット・ペルソナ】\n{persona_text}\n\n【求人原稿（文字数: 約{char_count}文字）】\n{combined_draft}{intent_section}{keyword_section}\n\n【物理的な読解時間データ】\n・流し読み想定: {skim_time_str}\n・熟読想定: {deep_time_str}"""

            if target_platform == "AirWork":
                zoning_point = """3. **🔍 SEOと感情訴求のゾーニング**: AirWorkは項目ごとに入力欄が分かれています。「求人タイトル」「キャッチコピー」など検索・クリック獲得に直結する項目に効果的なキーワードが含まれているか、「お仕事について」「求める人材」などの本文で、アルゴリズム向けの機械的な言葉と求職者の心に響く感情的な言葉が適切に使い分けられているかを、項目ごとに具体的に指摘してください。"""
            elif target_platform == "Indeed":
                zoning_point = """3. **🔍 SEOと感情訴求のゾーニング**: Indeedは項目ごとに入力欄が分かれています。「求人タイトル」「キャッチコピー」など検索結果・クリック獲得に直結する項目に効果的なキーワードが含まれているか、「仕事内容」「求める人材」「アピールポイント」などの本文で、アルゴリズム向けの機械的な言葉と求職者の心に響く感情的な言葉が適切に使い分けられているかを、項目ごとに具体的に指摘してください。"""
            else:
                zoning_point = """3. **🔍 SEOと感情訴求のゾーニング（サンドイッチ構造）**: 「アルゴリズム（機械）向けの言葉」と「求職者（人）向けの言葉」が混ざっていないかを評価します。「上部（SEO兼フック）」「中部（感情訴求・ストーリー）」「下部（SEO兼事務的条件）」のサンドイッチ構造で明確に棲み分けができているかを分析してください。"""

            prompt1 = f"""{CONTEXT}\n上記の前提を踏まえ、以下の3点について見やすいMarkdown形式で分析を出力してください。\n1. **⏱️ 読解タイム・コスト評価**: 物理的な読解時間を踏まえ、ペルソナの隙間時間に読まれる想定として適切か。\n2. **🔄 Before/After の伝達度**: ペルソナの「現状の悩み」から「入社後の変化」のコントラストが鮮明に描かれているか。（※作成の意図があれば、その成功度も評価）ただし、コントラストを鮮明にするために前職への批判や、過度にネガティブ・不安を煽る表現（例:「放任されていた」「社会保険にも入っていない」等を強調する言い回し）を使っている場合は、それは高評価ではなく、誠実さを欠く表現として明確に指摘してください。\n{zoning_point}"""

            # 【重要】AI呼び出しの前に入力内容を保存しておく。呼び出し後に保存すると、
            # 生成が完了する前に接続が切れた場合、そこまで入力した内容ごと失われてしまう。
            new_input_data = {
                "persona_text": persona_text,
                "target_keywords": target_keywords,
                "target_platform": target_platform,
                "title_rule": title_rule,
                "catch_rule": catch_rule,
                "draft_intent": draft_intent,
            }
            if target_platform == "AirWork":
                new_input_data["employment_type"] = employment_type
                new_input_data["airwork_fields"] = airwork_values
            elif target_platform == "Indeed":
                new_input_data["indeed_fields"] = indeed_values
            else:
                new_input_data["draft_text"] = draft_text

            st.session_state.input_data = new_input_data
            save_backup()

            response = call_ai(prompt1, "STEP 1", step_number=1)
            if response:
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

        if _d.get("target_platform") == "AirWork" and _d.get("airwork_fields"):
            _af = _d["airwork_fields"]
            _emp = _d.get("employment_type", "正社員")
            _full_title = build_full_airwork_title(_af, _emp)
            _title_text = _af.get("title", "")
            st.write(f"**求人タイトル**（自由入力部分: {len(_title_text)}/30文字。実際の表示は下記）")
            st.text(_full_title)
            st.write(f"**キャッチコピー**（{len(_af.get('catch', ''))}/30文字）")
            st.text(_af.get("catch", ""))
            for key, label, limit, _height in AIRWORK_FIELDS:
                _val = _af.get(key, "")
                _limit_str = f"{len(_val)}/{limit}文字" if limit else f"{len(_val)}文字"
                st.write(f"**{label}**（{_limit_str}）")
                st.text(_val)
        elif _d.get("target_platform") == "Indeed" and _d.get("indeed_fields"):
            _inf = _d["indeed_fields"]
            st.write(f"**求人タイトル**（{len(_inf.get('title', ''))}/30文字）")
            st.text(_inf.get("title", ""))
            st.write(f"**キャッチコピー**（{len(_inf.get('catch', ''))}/80文字）")
            st.text(_inf.get("catch", ""))
            for key, label, limit, _height in INDEED_FIELDS:
                _val = _inf.get(key, "")
                _limit_str = f"{len(_val)}/{limit}文字" if limit else f"{len(_val)}文字"
                st.write(f"**{label}**（{_limit_str}）")
                st.text(_val)
        else:
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
                v_preview = get_draft_preview(v["input_data"])
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
        response = call_ai(prompt2, "STEP 2", step_number=2)
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
        response = call_ai(prompt3, "STEP 3", step_number=3)
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

        if target_platform == "AirWork":
            employment_type = _d.get("employment_type", "正社員")
            field_limit_lines = "\n".join(
                f"・{label}: 上限{limit}文字" if limit else f"・{label}: 文字数上限なし"
                for label, limit in [("求人タイトル（自由入力部分。「【" + employment_type + "】」は含めない）", 30), ("キャッチコピー", 30)]
                + [(l, lim) for _, l, lim, _h in AIRWORK_FIELDS]
            )
            prompt4 = f"""最後のステップです。これまでのすべての分析と総合評価の課題を踏まえて、最高の結果を出すための【改善コピー提案】を出力してください。

【AirWorkの各入力項目と文字数上限】
{field_limit_lines}
※求人タイトルは「【{employment_type}】」がAirWork側の仕様で自動的に先頭へ付与されます。あなたが提案するのはその後に続く自由入力部分のみとし、必ず上記の文字数に収めてください。

**✨ 具体的な改善コピー提案**:
以下13項目それぞれについて、そのまま入力欄にコピペして使えるレベルの改善案を、各項目の文字数上限を厳守して提示してください。作成者の意図を汲み取りつつ、これまでの採点で減点された部分を補ってください。各項目名を見出しとして明記し、Markdown形式で出力してください。
※ペルソナの潜在ニーズに応えることは重要ですが、前職への批判や、「放任されていた」「社会保険にも入っていなかった」等を強調するような過度にネガティブ・不安を煽る表現は使わないでください。誠実で前向きな言葉で、入社後の魅力が自然に伝わる表現にしてください。
1. 求人タイトル（自由入力部分のみ）
2. キャッチコピー
3. お仕事について
4. 求める人材
5. 勤務地
6. 給与
7. 勤務時間
8. 休日休暇
9. 社会保険/福利厚生
10. 職場環境
11. 試用・研修期間
12. 応募とその後の流れ
13. 会社情報"""
        elif target_platform == "Indeed":
            field_limit_lines = "\n".join(
                f"・{label}: 上限{limit}文字" if limit else f"・{label}: 文字数上限なし"
                for label, limit in [("求人タイトル", 30), ("キャッチコピー", 80)]
                + [(l, lim) for _, l, lim, _h in INDEED_FIELDS]
            )
            prompt4 = f"""最後のステップです。これまでのすべての分析と総合評価の課題を踏まえて、最高の結果を出すための【改善コピー提案】を出力してください。

【Indeedの各入力項目と文字数上限】
{field_limit_lines}

【求人タイトルの判定基準】
{title_rule}

**✨ 具体的な改善コピー提案**:
以下20項目それぞれについて、そのまま入力欄にコピペして使えるレベルの改善案を、文字数上限がある項目（求人タイトル・キャッチコピー）は必ず厳守して提示してください。作成者の意図を汲み取りつつ、これまでの採点で減点された部分を補ってください。各項目名を見出しとして明記し、Markdown形式で出力してください。
※ペルソナの潜在ニーズに応えることは重要ですが、前職への批判や、「放任されていた」「社会保険にも入っていなかった」等を強調するような過度にネガティブ・不安を煽る表現は使わないでください。誠実で前向きな言葉で、入社後の魅力が自然に伝わる表現にしてください。
1. 求人タイトル
2. キャッチコピー
3. 仕事内容
4. 求める人材
5. アピールポイント
6. 勤務地・曜日
7. 勤務形態
8. 休暇休日
9. 勤務地所在地
10. 勤務地備考
11. アクセス
12. 給与
13. 試用期間
14. 待遇福利厚生
15. 社会保険
16. 企業名
17. 本社所在地
18. 業種
19. 代表者
20. その他"""
        else:
            prompt4 = f"""最後のステップです。これまでのすべての分析と総合評価の課題を踏まえて、最高の結果を出すための【改善コピー提案】を出力してください。

【適用する厳格なルール（掲載媒体: {target_platform}）】
・求人タイトルのルール: {title_rule}
・キャッチコピーのルール: {catch_rule}
※上記のルールは絶対厳守してください。媒体ポリシーの違反は致命的なエラーとなります。

**✨ 具体的な改善コピー提案**: 
作成者の意図を汲み取りつつ、採点で減点された部分を補い、そのまま元の原稿にコピペして使えるレベルの「具体的な文章案」を提示してください。
必ず、以下の【サンドイッチ構造】で原稿を再構築してください。
1. **上部（SEO兼フックゾーン）**: 検索キーワードを箇条書きや短い文章で配置し、アルゴリズムと初期クリックを稼ぐ。
2. **中部（感情訴求・ストーリーゾーン）**: SEOから完全に切り離し、人の心を動かす心地よい自然な言葉で、ペルソナの悩みをどう解決するかを書き切る。ただし、前職への批判や、「放任されていた」「社会保険にも入っていなかった」等を強調するような過度にネガティブ・不安を煽る表現は使わないこと。誠実で前向きな言葉で、潜在ニーズに応える表現にすること。
3. **下部（SEO兼事務的条件ゾーン）**: 求める人材や福利厚生など、アルゴリズムに対するキーワードの網羅性を担保する。

見出しには検索キーワードを組み込み、感情は検索キーワードに翻訳（言い換え）して配置すること。プロのコピーライターとして、魅力を最大化した実際の文章を提示してください。"""
        response = call_ai(prompt4, "STEP 4", step_number=4)
        if response:
            st.session_state.results[4] = response
            st.session_state.current_step = 4
            save_backup()
            st.rerun()

if st.session_state.current_step >= 4:
    st.markdown("### ✨ STEP 4. 具体的な改善コピー提案（そのまま使える修正案）")
    st.markdown(f'<div class="result-block">{st.session_state.results.get(4, "")}</div>', unsafe_allow_html=True)
    st.success("✅ 全ての分析と改善提案が完了しました！この内容で原稿を直してすぐ再評価したい場合は上の「✏️ 原稿を修正してもう一度評価する」を、まったく別の原稿を評価する場合は一番上の「🗑️ まったく新しい原稿を評価する」を押してください。")
