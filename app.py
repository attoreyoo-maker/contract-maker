import base64
import html
import io
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image
from supabase import create_client

st.set_page_config(page_title="[문의 답변 초안]")

# 챗봇 — helper.py 와 같은 방식으로 Gemini 를 부른다
MODEL = "gemini-3.5-flash-lite"
TIMEOUT_MS = 60000  # 60초 안에 답이 없으면 멈추고 오류를 보여 준다

# 챗봇 말투 — 대화창에서 고른 말투의 설명을 고정 지시문 뒤에 붙여 보낸다
TONES = {
    "친절한 존댓말": "'~하시면 돼요', '~해 주세요'처럼 상대를 배려하는 부드럽고 친절한 존댓말로 답한다.",
    "정중한 존댓말": "'~합니다', '~하십시오', '~드립니다'처럼 격식을 갖춘 정중한 존댓말로 답한다. '~해요'는 쓰지 않는다.",
    "친근한 존댓말": "'~해요', '~하면 돼요!'처럼 가까운 이웃에게 말하듯 가볍고 친근한 존댓말로 답한다. '~하십시오', '~드립니다'는 쓰지 않는다.",
}
KST = timezone(timedelta(hours=9))  # 한국 시각
load_dotenv()

SCREEN_1 = "화면 1 - 계약서 만들기"
SCREEN_2 = "화면 2 - 계약서 목록"
SCREEN_3 = "화면 3 - 양식·거래처 고르기"

# 앱을 열면 화면 2(계약서 목록)가 먼저 보인다 (PRD 사용자 흐름)
if "screen" not in st.session_state:
    st.session_state.screen = SCREEN_2
if "step" not in st.session_state:
    st.session_state.step = 1


# data 폴더 샘플 자료 (빈칸은 "(빈칸)"으로 보여 줌)
DATA = Path(__file__).parent / "data"


def load(name):
    return pd.read_csv(DATA / name, dtype=str).fillna("(빈칸)")


contracts = load("contracts.csv")
templates = load("templates.csv")
partners = load("partners.csv")


def contract_html(partner, amount, date, content):
    """계약서를 브라우저로 여는 .html 파일 내용으로 만든다 (Ctrl+P 로 인쇄·PDF 저장 가능)"""
    p, a, d, c = (html.escape(v) for v in (partner, amount, date, content))
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>계약서</title>
<style>
  body {{ font-family: "Malgun Gothic", sans-serif; max-width: 640px; margin: 48px auto; line-height: 2; }}
  h1 {{ text-align: center; letter-spacing: 0.5em; }}
  th {{ text-align: left; padding-right: 24px; font-weight: normal; }}
</style></head><body>
<h1>계약서</h1>
<table>
  <tr><th>거래처명 (을)</th><td>{p}</td></tr>
  <tr><th>계약 금액</th><td>{a}</td></tr>
  <tr><th>계약 날짜</th><td>{d}</td></tr>
  <tr><th>계약 내용</th><td>{c}</td></tr>
</table>
<p>위 내용으로 계약을 맺습니다.</p>
<p>갑&nbsp; 상호 ____________&nbsp; 서명 ____________<br>
을&nbsp; 상호 {p}&nbsp; 서명 ____________</p>
</body></html>"""


def file_name(partner, date):
    """계약서_거래처명_날짜 — 파일 이름으로 쓸 수 없는 글자는 _ 로 바꾼다"""
    return re.sub(r'[\\/:*?"<>|]', "_", f"계약서_{partner}_{date}") + ".html"


def go(screen, step=1):
    st.session_state.screen = screen
    st.session_state.step = step


@st.cache_data
def bot_icon():
    """idea/bot.png.png 에서 로봇 얼굴 부분만 잘라 작게 줄인다 (새 파일은 만들지 않음)"""
    image = Image.open(Path(__file__).parent / "idea" / "bot.png.png")
    image = image.crop((190, 40, 960, 810)).resize((160, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def show_answer(where, text):
    """AI 답을 보여 주고, 답 옆에 한 번에 복사하는 버튼을 붙인다"""
    with where.chat_message("assistant", avatar=bot_icon()):
        left, right = st.columns([5, 1])
        left.markdown(text.replace("\n", "  \n"))  # 줄바꿈이 화면에서도 보이게
        with right:
            st.html(
                f"""<button class="copy-answer" title="답 복사하기"
                    onclick='navigator.clipboard.writeText({html.escape(json.dumps(text), quote=True)})
                             .then(() => {{ this.textContent = "복사됨"; }})'>복사</button>""",
                unsafe_allow_javascript=True,
            )


def chatbot():
    """오른쪽 아래 챗봇 아이콘 — 누르면 대화창이 열리고, PRD.md 를 읽고 서비스에 대해 답한다"""
    icon = base64.b64encode(bot_icon()).decode()
    st.html(f"""<style>
      .st-key-chatbot {{ position: fixed; right: 24px; bottom: 24px; z-index: 1000; width: auto; }}
      .st-key-chatbot button {{ width: 72px; height: 72px; padding: 0; border-radius: 50%;
                               background: url(data:image/png;base64,{icon}) center / cover;
                               box-shadow: 0 4px 12px rgba(0,0,0,.25); }}
      .st-key-chatbot button * {{ display: none; }}
      .copy-answer {{ font-size: 12px; padding: 2px 8px; border: 1px solid #ccc;
                      border-radius: 6px; background: white; cursor: pointer; white-space: nowrap; }}
    </style>""")
    if "chat" not in st.session_state:
        st.session_state.chat = []          # 지금까지 주고받은 말
        st.session_state.chat_last_id = None  # 이어서 대화하려고 Gemini 가 준 앞 대화 번호

    with st.container(key="chatbot"):
        with st.popover("챗봇"):
            st.markdown("**계약서 만들기 도우미**")
            tone = st.selectbox("말투", list(TONES), key="chat_tone")
            history = st.container(height=320)
            with history:
                st.chat_message("assistant", avatar=bot_icon()).write("안녕하세요! 계약서 만들기에 대해 궁금한 걸 물어보세요.")
                for role, text in st.session_state.chat:
                    if role == "assistant":
                        show_answer(history, text)
                    else:
                        st.chat_message(role).write(text)

            question = st.chat_input("물어볼 말", key="chat_question")
            if question:
                answer = ask(question, tone, history)
                # 물은 말과 받은 답을 Supabase chat_logs 표에 남긴다
                save_chat(tone, question, answer)

            # 대화창 아래 — chat_logs 표에 남은 지난 대화 목록
            past_chats()


def ask(question, tone, history):
    """물은 말을 Gemini 에 보내고 받은 답을 대화창에 보여 준 뒤 돌려준다"""
    history.chat_message("user").write(question)
    st.session_state.chat.append(("user", question))

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        answer = "GEMINI_API_KEY 가 비어 있습니다. .env 에 넣어 주세요."
    else:
        # 고정 지시문은 chatbot_prompt.txt 에 있다 — 지시문을 바꿀 때는 그 파일만 고친다
        instruction = (Path(__file__).parent / "chatbot_prompt.txt").read_text(encoding="utf-8").strip()
        prd = (Path(__file__).parent / "PRD.md").read_text(encoding="utf-8")
        # 두 번째 질문부터는 앞 대화 번호를 함께 보내 앞에서 한 말을 기억하게 한다
        earlier = {}
        if st.session_state.chat_last_id:
            earlier["previous_interaction_id"] = st.session_state.chat_last_id
        try:
            with history, st.spinner("답을 쓰는 중..."):
                client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
                interaction = client.interactions.create(
                    model=MODEL,
                    input=question,
                    system_instruction=instruction + "\n\n[말투]\n" + TONES[tone] + "\n\n" + prd,
                    **earlier,
                )
            st.session_state.chat_last_id = interaction.id
            # Gemini 가 가끔 글자 없이 빈 답을 보낼 때가 있다
            answer = interaction.output_text or "답을 받지 못했습니다.\n같은 말을 한 번 더 보내 주세요.\n그래도 안 되면 질문을 조금 바꿔 보세요."
        except Exception as e:
            answer = f"Gemini 를 부르지 못했습니다: {e}"
    show_answer(history, answer)
    st.session_state.chat.append(("assistant", answer))
    return answer


@st.cache_resource
def connect(url, key):
    return create_client(url, key)


def chat_table():
    """Supabase chat_logs 표 — 공개용 키(SUPABASE_KEY)를 쓴다. 관리자 키를 여기에 쓰지 말 것"""
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        return None
    return connect(url, key)


def save_chat(tone, question, answer):
    """물은 말과 받은 답을 chat_logs 표에 한 줄로 남긴다"""
    supabase = chat_table()
    if supabase is None:
        return
    try:
        supabase.table("chat_logs").insert(
            {"tone": tone, "question": question, "answer": answer}, returning="minimal"
        ).execute()
    except Exception as e:
        st.caption(f"대화를 Supabase 에 남기지 못했습니다: {e}")


def past_chats():
    """chat_logs 표에 남은 지난 대화를 최근 것부터 20개 보여 준다"""
    st.markdown("**지난 대화 목록**")
    supabase = chat_table()
    if supabase is None:
        st.caption(".env 에 SUPABASE_URL 과 SUPABASE_KEY 를 넣으면 지난 대화가 여기에 보입니다.")
        return
    try:
        rows = (
            supabase.table("chat_logs")
            .select("created_at, tone, question, answer")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
            .data
        )
    except Exception as e:
        st.caption(f"지난 대화를 불러오지 못했습니다: {e}")
        return
    if not rows:
        st.caption("아직 남은 대화가 없습니다.")
        return
    with st.container(height=240):
        for row in rows:
            # Supabase 는 세계 표준 시각으로 주므로 한국 시각(+9시간)으로 바꿔 보여 준다
            when = datetime.fromisoformat(row["created_at"]).astimezone(KST).strftime("%m.%d %H:%M")
            with st.expander(f"{when} · {row['question'][:25]}"):
                st.caption(f"말투: {row['tone']}")
                st.markdown(f"**물은 말** {row['question']}")
                st.markdown(row["answer"].replace("\n", "  \n"))


# 이 서비스가 해 주는 일 (한 줄)
st.sidebar.write("받은 문의를 붙여 넣으면 답변 초안을 만들어 줍니다.")

# 세 화면 오가기
st.sidebar.radio("화면", [SCREEN_1, SCREEN_2, SCREEN_3], key="screen")

# 어느 화면에서든 오른쪽 아래에 챗봇이 보인다
chatbot()

if st.session_state.screen == SCREEN_1:
    st.warning("아직 예시 결과입니다")
    st.title("계약서 만들기")

    # 넣는 자리
    st.text_input("거래처명", placeholder="예: (주)한빛상사")
    st.text_input("금액", placeholder="예: 5,000,000원")
    st.text_input("날짜", placeholder="예: 2026.09.17")
    st.text_area("계약내용", placeholder="계약 조건 및 상세 내용 입력")

    # 버튼 (아직 누르면 아무 일도 일어나지 않음)
    st.button("만들기", width="stretch")

    # 결과 자리 (예시 하나)
    partner, amount, date, content = "(주)한빛상사", "5,000,000원", "2026.09.17", "상품 납품"
    st.code(
        f"""                계약서

  거래처명 (을)  : {partner}
  계약 금액      : {amount}
  계약 날짜      : {date}
  계약 내용      : {content}

  위 내용으로 계약을 맺습니다.

  갑  상호 ____________  서명 ____________
  을  상호 {partner}  서명 ____________""",
        language=None,
    )

    # 다운로드 — PRD 는 .pdf 이지만, 도구 설치 없이 지금은 .html 로 내려받는다
    if st.download_button("다운로드", contract_html(partner, amount, date, content),
                          file_name=file_name(partner, date), mime="text/html",
                          width="stretch"):
        st.success("다운로드 완료")

elif st.session_state.screen == SCREEN_2:
    st.warning("아직 예시 결과입니다")
    st.title("계약서 목록")

    # 목록 (data/contracts.csv) — 항목을 선택하면 화면 1로 간다
    for i, row in contracts.iterrows():
        st.button(f"{row.partner}  ·  {row.amount}  ·  {row.date}", width="stretch",
                  key=f"contract_{i}", on_click=go, args=(SCREEN_1,))

    st.button("+ 계약서 새로 만들기", width="stretch", on_click=go, args=(SCREEN_3,))

else:
    st.warning("아직 예시 결과입니다")
    st.title("양식·거래처 선택")

    step = st.session_state.step
    st.caption(("**① 양식 고르기**" if step == 1 else "① 양식 고르기")
               + "  ─────  "
               + ("**② 거래처 고르기**" if step == 2 else "② 거래처 고르기"))

    if step == 1:
        st.radio("저장된 양식 목록", templates["name"].tolist(),
                 index=None, key="form")
    else:
        st.radio("저장된 거래처 목록", partners["name"].tolist(),
                 index=None, key="partner")

    left, right = st.columns(2)
    left.button("목록으로 돌아가기", width="stretch", on_click=go, args=(SCREEN_2,))
    if step == 1:
        right.button("다음", width="stretch", on_click=go, args=(SCREEN_3, 2))
    else:
        right.button("적용", width="stretch", on_click=go, args=(SCREEN_1,))
