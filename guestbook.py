import os

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

st.set_page_config(page_title="한 줄 방명록")

# .env 의 SUPABASE_URL, SUPABASE_KEY 를 읽어 Supabase 에 연결
load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
if not url or not key:
    st.error(".env 에 SUPABASE_URL 과 SUPABASE_KEY 를 넣어 주세요.")
    st.stop()

supabase = create_client(url, key)

st.title("한 줄 방명록")

# 글 쓰기 — 남기기를 누르면 guestbook 표에 한 줄 추가
with st.form("write", clear_on_submit=True):
    content = st.text_input("한 줄 남기기", max_chars=100)
    if st.form_submit_button("남기기"):
        if content.strip():
            supabase.table("guestbook").insert({"message": content.strip()}).execute()
            st.success("글을 남겼습니다.")
        else:
            st.warning("글을 넣지 않았습니다.")

# 글 목록 — 최근 글이 위로
rows = (
    supabase.table("guestbook")
    .select("message, created_at")
    .order("created_at", desc=True)
    .execute()
    .data
)

st.subheader(f"지금까지 쌓인 글 : {len(rows)}줄")
if not rows:
    st.caption("아직 남긴 글이 없습니다.")
for row in rows:
    st.write(f"{row['created_at'][:16].replace('T', ' ')} · {row['message']}")
