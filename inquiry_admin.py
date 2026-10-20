import os

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

st.set_page_config(page_title="문의 답변")

# 내 답변 화면 — 관리자 키(SUPABASE_SERVICE_KEY)를 쓴다. 내 컴퓨터에서만 실행할 것
load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")
if not url or not key:
    st.error(".env 에 SUPABASE_URL 과 SUPABASE_SERVICE_KEY 를 넣어 주세요.")
    st.stop()

supabase = create_client(url, key)

st.title("문의 답변")

show = st.radio("보기", ["대기", "완료"], horizontal=True)

# 고른 상태의 문의만, 최근 것이 위로
rows = (
    supabase.table("inquiries")
    .select("*")
    .eq("status", show)
    .order("date", desc=True)
    .execute()
    .data
)

st.subheader(f"{show} 문의 : {len(rows)}건")
if not rows:
    st.caption(f"{show} 문의가 없습니다.")

for row in rows:
    with st.expander(f"{row['date']} · {row['type']} · {row['message'][:30]}"):
        st.write(row["message"])
        draft = st.text_area("답변 초안", value=row["draft"] or "", key=f"draft_{row['id']}")
        left, right = st.columns(2)
        if left.button("초안 저장", key=f"save_{row['id']}"):
            supabase.table("inquiries").update({"draft": draft}).eq("id", row["id"]).execute()
            st.success("초안을 저장했습니다.")
        if show == "대기" and right.button("완료로 바꾸기", key=f"done_{row['id']}"):
            supabase.table("inquiries").update({"draft": draft, "status": "완료"}).eq("id", row["id"]).execute()
            st.rerun()
