import anthropic
import streamlit as st
from dotenv import load_dotenv
from keys import get_key

MODEL = "claude-haiku-5-5"
TIMEOUT = 60  # 60초 안에 답이 없으면 멈추고 오류를 보여 준다

st.set_page_config(page_title="챗봇")

# .env 의 ANTHROPIC_API_KEY 가 채워져 있는지만 확인 (키 값은 화면에 보이지 않음)
load_dotenv()
api_key = get_key("ANTHROPIC_API_KEY", "").strip()

st.title("챗봇")

if api_key:
    st.success("ANTHROPIC_API_KEY 가 채워져 있습니다.")
else:
    st.error("ANTHROPIC_API_KEY 가 비어 있습니다. .env 에 넣어 주세요.")
    st.stop()

# 보내기를 누르면 빈칸의 말을 Claude 에 보내고 받은 답을 보여 준다
question = st.text_input("물어볼 말")
if st.button("보내기"):
    if not question.strip():
        st.warning("말을 넣지 않았습니다.")
    else:
        try:
            with st.spinner("Claude가 답을 하는 중..."):
                client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT)
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=16000,
                    output_config={"effort": "low"},  # 간단한 대화라 생각을 짧게 해서 빠르고 싸게 답한다
                    messages=[{"role": "user", "content": question.strip()}],
                )
            if response.stop_reason == "refusal":
                st.warning("Claude 가 이 질문에는 답하지 않았습니다. 질문을 바꿔 보세요.")
            else:
                st.write("".join(b.text for b in response.content if b.type == "text"))
            usage = response.usage
            st.caption(
                f"이번 요청에 쓴 토큰: 모두 {usage.input_tokens + usage.output_tokens}개 "
                f"(보낸 말 {usage.input_tokens} · 받은 답 {usage.output_tokens})"
            )
        except anthropic.AuthenticationError:
            st.error("ANTHROPIC_API_KEY 가 올바르지 않습니다. .env 의 키를 확인해 주세요.")
        except anthropic.APIError as e:
            st.error(f"Claude 를 부르지 못했습니다: {e}")
