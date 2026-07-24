import streamlit as st
from common import init_session_state, get_api_key, reset_all

st.set_page_config(
    page_title="求人原稿スコアリングアプリ",
    page_icon="📝",
    layout="wide",
)

init_session_state()

api_key = get_api_key()
if not api_key:
    st.error("⚠️ Anthropic APIキーが設定されていません。右上のSettings > Secretsから登録してください。")
    st.stop()
st.session_state.anthropic_api_key = api_key

with st.sidebar:
    st.markdown("### 📝 求人原稿スコアリング")
    st.caption("原稿入力 → 読解コスト・構成評価 → 総合評価・改善コピー の順にお使いください。")
    st.markdown("---")
    if st.button("🗑️ まったく新しい原稿を評価する（すべてクリア）", use_container_width=True):
        reset_all()
        st.rerun()

pg = st.navigation([
    st.Page("pages/1_input.py", title="原稿入力", icon="📝"),
    st.Page("pages/2_readability.py", title="読解コスト・構成評価", icon="🔍"),
    st.Page("pages/3_final_review.py", title="総合評価・改善コピー", icon="✨"),
])
pg.run()
