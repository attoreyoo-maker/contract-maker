import os

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

MODEL = "gemini-3.5-flash-lite"
TIMEOUT_MS = 60000  # 60초 안에 답이 없으면 멈추고 오류를 보여 준다

st.set_page_config(page_title="챗봇")

# .env 의 GEMINI_API_KEY 가 채워져 있는지만 확인 (키 값은 화면에 보이지 않음)
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY", "").strip()

st.title("챗봇")

if api_key:
    st.success("GEMINI_API_KEY 가 채워져 있습니다.")
else:
    st.error("GEMINI_API_KEY 가 비어 있습니다. .env 에 넣어 주세요.")
    st.stop()

# 보내기를 누르면 빈칸의 말을 Gemini 에 보내고 받은 답을 보여 준다
question = st.text_input("물어볼 말")
if st.button("보내기"):
    if not question.strip():
        st.warning("말을 넣지 않았습니다.")
    else:
        try:
            with st.spinner("Gemini가 답을 하는 중..."):
                client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
                interaction = client.interactions.create(model=MODEL, input=question.strip())
            st.write(interaction.output_text)
            usage = interaction.usage
            if usage:
                st.caption(
                    f"이번 요청에 쓴 토큰: 모두 {usage.total_tokens or 0}개 "
                    f"(보낸 말 {usage.total_input_tokens or 0} · 받은 답 {usage.total_output_tokens or 0})"
                )
        except Exception as e:
            st.error(f"Gemini 를 부르지 못했습니다: {e}")
