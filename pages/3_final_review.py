import streamlit as st
from common import render_header, call_ai, AIRWORK_FIELDS, INDEED_FIELDS

render_header("✨ 総合評価・改善コピー", "STEP3: 総合評価とCV期待度 → STEP4: 具体的な改善コピー提案")

if st.session_state.current_step < 2:
    st.warning("⚠️ まずは「🔍 読解コスト・構成評価」ページでSTEP1・STEP2を完了させてから、このページに進んでください。")
    st.stop()

with st.expander("📋 STEP1・STEP2の結果を振り返る", expanded=False):
    st.markdown(f'<div class="result-block">{st.session_state.results.get(1, "")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="result-block">{st.session_state.results.get(2, "")}</div>', unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

# ── STEP3: 総合評価とCV期待度 ─────────────────────────────────
if st.session_state.current_step == 2:
    if st.button("🏆 STEP 3: 総合評価とCV期待度の算出を実行", use_container_width=True):
        prompt3 = """ありがとうございます。次に、これまでの分析を総括し、以下の項目を出力してください。\n**🏆 総合評価**: 目標である「ペルソナ層からの応募 月5件以上」を見込めるか、総合的な「CV期待度スコア（100点満点）」を提示し、現状の課題に関する結論を論理的に述べてください。※具体的な改善コピーの作成は次のステップで行うので、ここでは課題の総括にとどめてください。"""
        response = call_ai(prompt3, "STEP 3")
        if response:
            st.session_state.results[3] = response
            st.session_state.current_step = 3
            st.rerun()

if st.session_state.current_step >= 3:
    st.markdown("### 🏆 STEP 3. 総合評価とCV期待度")
    st.markdown(f'<div class="result-block">{st.session_state.results.get(3, "")}</div>', unsafe_allow_html=True)

# ── STEP4: 具体的な改善コピー提案 ─────────────────────────────
if st.session_state.current_step == 3:
    if st.button("✨ STEP 4: 具体的な改善コピー提案を生成", use_container_width=True):
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
                for label, limit in [("求人タイトル", 30)]
                + [(l, lim) for _, l, lim, _h in INDEED_FIELDS]
            )
            field_limit_lines = f"・キャッチコピー: 60文字以上70文字以内（この範囲を厳守すること）\n{field_limit_lines}"
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

        response = call_ai(prompt4, "STEP 4")
        if response:
            st.session_state.results[4] = response
            st.session_state.current_step = 4
            st.rerun()

if st.session_state.current_step >= 4:
    st.markdown("### ✨ STEP 4. 具体的な改善コピー提案（そのまま使える修正案）")
    st.markdown(f'<div class="result-block">{st.session_state.results.get(4, "")}</div>', unsafe_allow_html=True)
    st.success("✅ 全ての分析と改善提案が完了しました！この内容で原稿を直してすぐ再評価したい場合は「📝 原稿入力」ページで内容を書き直して保存してください。まったく別の原稿を評価する場合は、左サイドバーの「🗑️ まったく新しい原稿を評価する」を押してください。")
