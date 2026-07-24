"""
求人原稿 添削・スコアリングエージェント ── 共通モジュール
3ページ(原稿入力 / 読解コスト・構成評価 / 総合評価・改善コピー)から共通で読み込む。
"""
import streamlit as st
import anthropic
import os
import math
import json

# ── 共通CSS・ヘッダー ────────────────────────────────────────────
GLOBAL_CSS = """
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
"""

def render_header(title: str, subtitle: str):
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    st.markdown(f"""
<div class="app-header">
    <h1>{title}</h1>
    <p>{subtitle}</p>
</div>
""", unsafe_allow_html=True)

# ── APIキー取得 ─────────────────────────────────────────────────
def get_api_key():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets["ANTHROPIC_API_KEY"]
        except Exception:
            return None
    return api_key

# ── セッション状態の初期化 ───────────────────────────────────────
def init_session_state():
    defaults = {
        "current_step": 0,
        "ai_messages": [],
        "results": {},
        "input_data": {},
        "history": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # 【重要】ここで復元するのは「入力した原稿・ペルソナなど」だけに絞る。
    # AIの生成結果(results)や会話履歴(ai_messages)は対象外。生成途中の内容を
    # 追いかけて保存・復元しようとすると、直しても直しても別の不具合を生む
    # 泥沼になることが分かっているため、あえてシンプルな範囲にとどめている。
    # 万一結果が消えた場合は、該当STEPのボタンをもう一度押せば再生成できる。
    if not st.session_state.input_data:
        _backup = load_input_backup()
        if _backup:
            st.session_state.input_data = _backup

def reset_all():
    """完全リセット(新しい原稿の評価を最初から始める)"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    clear_input_backup()

def archive_current_version():
    """現在の入力内容と分析結果を改訂履歴に保存する(修正サイクルで前バージョンを失わないため)"""
    if st.session_state.results:
        st.session_state.history.append({
            "input_data": dict(st.session_state.input_data),
            "results": dict(st.session_state.results),
        })

# ── 入力内容の軽量バックアップ(AIの生成結果は対象外) ──────────────
INPUT_BACKUP_FILE = "streamlit_scoring_input_backup.json"

def save_input_backup():
    tmp_file = INPUT_BACKUP_FILE + ".tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(st.session_state.input_data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, INPUT_BACKUP_FILE)
    except Exception:
        pass

def load_input_backup():
    if os.path.exists(INPUT_BACKUP_FILE):
        try:
            with open(INPUT_BACKUP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def clear_input_backup():
    try:
        if os.path.exists(INPUT_BACKUP_FILE):
            os.remove(INPUT_BACKUP_FILE)
    except Exception:
        pass

# ── システムプロンプト・ペルソナのデフォルト例文 ───────────────────
default_persona = """30歳 販売業に携わる女性\n接客の仕事は好きで続けたいが、不規則な勤務シフトでの働き方を脱するためにキャリアチェンジを希望している。"""

SYSTEM_PROMPT = "あなたは採用マーケティングとSEOの第一人者です。ペルソナの心理に基づき、辛口かつ論理的、建設的に原稿を評価してください。冗長な前置きや挨拶は不要です。即座に本題に入ってください。ペルソナの潜在的なニーズや不安に訴えることは重要ですが、それを理由に前職への批判や『放任されていた』『社会保険にも入っていない』のような、過度にネガティブで不安を煽る表現を評価文中や改善提案で使うことは避けてください。ネガティブな感情を煽って引き寄せるのではなく、誠実でポジティブな言葉で潜在ニーズに応える表現を一貫して用いてください。"

# 採点・分析タスクは「創造性」より「再現性」を優先するため、温度を低めに固定する。
EVAL_TEMPERATURE = 0.2

# ── AirWork入力項目の定義 ──────────────────────────────────────
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
    return f"【{employment_type}】{af.get('title', '')}"

def validate_airwork_fields(af, employment_type):
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

# ── Indeed入力項目の定義 ───────────────────────────────────────
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
    errors = []
    if len(inf.get("title", "")) > 30:
        errors.append(f"求人タイトル: {len(inf.get('title', ''))}文字（上限30文字）")
    if len(inf.get("catch", "")) > 70:
        errors.append(f"キャッチコピー: {len(inf.get('catch', ''))}文字（60文字以上70文字以内）")
    for key, label, limit, _ in INDEED_FIELDS:
        if limit and len(inf.get(key, "")) > limit:
            errors.append(f"{label}: {len(inf.get(key, ''))}文字（上限{limit}文字）")
    return errors

def build_indeed_draft_text(inf):
    parts = [
        f"■求人タイトル（上限30文字/現在{len(inf.get('title', ''))}文字）\n{inf.get('title', '')}",
        f"■キャッチコピー（60文字以上70文字以内/現在{len(inf.get('catch', ''))}文字）\n{inf.get('catch', '')}",
    ]
    for key, label, limit, _ in INDEED_FIELDS:
        val = inf.get(key, "")
        limit_str = f"上限{limit}文字/現在{len(val)}文字" if limit else f"現在{len(val)}文字"
        parts.append(f"■{label}（{limit_str}）\n{val}")
    return "\n\n".join(parts)

def get_indeed_title_rule():
    return """30文字以内。Indeedの実際のガイドラインに基づき、以下を厳守すること。

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

def get_draft_preview(input_data, max_len=80):
    """改訂履歴のプレビュー用に、原稿の一部を取り出す(自由記述/AirWork/Indeed構造化の3対応)"""
    if input_data.get("airwork_fields"):
        text = input_data["airwork_fields"].get("job_content", "") or input_data["airwork_fields"].get("title", "")
    elif input_data.get("indeed_fields"):
        text = input_data["indeed_fields"].get("job_content", "") or input_data["indeed_fields"].get("title", "")
    else:
        text = input_data.get("draft_text", "")
    return text[:max_len] + "…" if len(text) > max_len else text

def build_combined_draft(input_data):
    """input_dataから、AIに渡す原稿全文を再構築する(ページ2・3で共通して使う)"""
    platform = input_data.get("target_platform", "")
    if platform == "AirWork":
        return build_airwork_draft_text(input_data.get("airwork_fields", {}), input_data.get("employment_type", "正社員"))
    elif platform == "Indeed":
        return build_indeed_draft_text(input_data.get("indeed_fields", {}))
    else:
        return input_data.get("draft_text", "")

# ── AI呼び出し(シンプルな逐次描画。生成中の高度な保存・間引きは行わない) ──
def call_ai(prompt, step_name):
    try:
        api_key = st.session_state.anthropic_api_key
        client = anthropic.Anthropic(api_key=api_key)
        st.session_state.ai_messages.append({"role": "user", "content": prompt})

        result_placeholder = st.empty()
        full_response = ""

        with st.spinner(f"{step_name} を実行中..."):
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=16384,
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
