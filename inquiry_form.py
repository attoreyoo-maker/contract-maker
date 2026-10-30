from datetime import date

import streamlit as st
from dotenv import load_dotenv
from keys import get_key
from supabase import create_client

st.set_page_config(page_title="문의 남기기")

# 손님용 화면 — 공개용 키(SUPABASE_KEY)만 쓴다. 관리자 키를 여기에 쓰지 말 것
load_dotenv()
url = get_key("SUPABASE_URL")
key = get_key("SUPABASE_KEY")
if not url or not key:
    st.error(".env 에 SUPABASE_URL 과 SUPABASE_KEY 를 넣어 주세요.")
    st.stop()

supabase = create_client(url, key)

st.title("문의 남기기")

# 남기기를 누르면 inquiries 표에 한 줄 추가 (손님은 넣기만 되고 읽기는 안 됨)
with st.form("inquiry", clear_on_submit=True):
    kind = st.selectbox("문의 종류", ["배송", "환불", "교환", "기타"])
    message = st.text_area("문의 내용", max_chars=500)
    if st.form_submit_button("남기기"):
        if message.strip():
            # 손님은 읽기 권한이 없으므로 넣은 글을 돌려받지 않는다(returning="minimal")
            supabase.table("inquiries").insert(
                {"date": date.today().isoformat(), "type": kind, "message": message.strip(), "status": "대기"},
                returning="minimal",
            ).execute()
            st.success("문의를 남겼습니다. 답변을 기다려 주세요.")
        else:
            st.warning("문의 내용을 넣지 않았습니다.")
