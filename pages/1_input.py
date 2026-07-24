import streamlit as st
from common import (
    render_header, default_persona, get_indeed_title_rule, get_draft_preview,
    archive_current_version, save_input_backup,
    EMPLOYMENT_TYPES, AIRWORK_FIELDS, INDEED_FIELDS,
    build_full_airwork_title, validate_airwork_fields,
    validate_indeed_fields,
)

render_header("📝 原稿入力", "求人原稿とターゲット・ペルソナを入力してください")

if st.session_state.history:
    st.info(f"✏️ 第{len(st.session_state.history) + 1}版を編集中です。前回の内容が反映されています。原稿を修正して保存してください。")

# 【重要】掲載メディアの選択は、以下の入力欄の表示形式(AirWork用13項目 or 自由記述)を
# その場で切り替える必要があるため、あえてフォームの外に置く。
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
    st.caption("📌 求人タイトル: 30文字以内（※職種名の一意性を厳守） / キャッチコピー: 60文字以上70文字以内 / その他18項目は下記フォームで個別に入力")
elif target_platform == "AirWork":
    st.caption("📌 求人タイトル: 自由入力部分30文字以内（雇用形態の自動付与部分は別途） / キャッチコピー: 30文字以内 / その他11項目は下記フォームで個別に入力")

with st.form("input_form", border=False):
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
            title_rule = get_indeed_title_rule()
            catch_rule = "60文字以上〜70文字以内"
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
                "キャッチコピー（60文字以上70文字以内）",
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
    submitted = st.form_submit_button("💾 この内容を保存する", use_container_width=True)

if submitted:
    if target_platform == "AirWork":
        validation_errors = validate_airwork_fields(airwork_values, employment_type)
        is_empty = not any(v.strip() for v in airwork_values.values())
    elif target_platform == "Indeed":
        validation_errors = validate_indeed_fields(indeed_values)
        is_empty = not any(v.strip() for v in indeed_values.values())
    else:
        validation_errors = []
        is_empty = not draft_text.strip()

    if is_empty:
        st.warning("⚠️ 評価する求人原稿を入力してください。")
    elif not persona_text.strip():
        st.warning("⚠️ ターゲット・ペルソナの詳細を入力してください。")
    elif validation_errors:
        st.error(
            "⚠️ 以下の項目が文字数の上限を超えています。修正のうえ、再度保存してください。\n\n"
            + "\n".join(f"- {e}" for e in validation_errors)
        )
    else:
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

        # 既存の分析結果があれば改訂履歴へアーカイブしてから、新しい版として仕切り直す
        if st.session_state.results:
            archive_current_version()
        st.session_state.input_data = new_input_data
        st.session_state.results = {}
        st.session_state.ai_messages = []
        st.session_state.current_step = 0
        save_input_backup()
        st.success("✅ 保存しました。左のナビゲーションから「🔍 読解コスト・構成評価」に進んでください。")

# ── 改訂履歴の表示 ──
if st.session_state.history:
    st.markdown("<hr>", unsafe_allow_html=True)
    with st.expander(f"📈 改訂履歴（過去{len(st.session_state.history)}版）", expanded=False):
        for i, v in enumerate(st.session_state.history):
            v_preview = get_draft_preview(v["input_data"])
            st.markdown(f"**第{i + 1}版**　`{v_preview}`")
            for step_no, step_label in [(1, "STEP1 読解コスト・構成"), (2, "STEP2 意思決定フロー採点"), (3, "STEP3 総合評価"), (4, "STEP4 改善コピー")]:
                if v["results"].get(step_no):
                    st.markdown(f"**└ {step_label}**")
                    st.markdown(f'<div class="result-block" style="padding:1rem 1.2rem; margin-top:0.3rem; margin-bottom:0.8rem;">{v["results"][step_no]}</div>', unsafe_allow_html=True)
            st.markdown("---")
