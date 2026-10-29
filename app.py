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
from PIL import Image, ImageDraw, ImageFont
from supabase import create_client

# 화면 가로 폭을 끝까지 쓴다
st.set_page_config(page_title="계약서 만들기", page_icon="💬", layout="wide")

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

SCREEN_1 = "화면 1 - 계약서 목록"
SCREEN_2 = "화면 2 - 양식·거래처 고르기"
SCREEN_3 = "화면 3 - 계약서 만들기"

# 앱을 열면 계약서 목록이 먼저 보인다 (PRD 사용자 흐름)
if "screen" not in st.session_state:
    st.session_state.screen = SCREEN_1
if "step" not in st.session_state:
    st.session_state.step = 1
if "history" not in st.session_state:
    st.session_state.history = []  # 지나온 화면 (화면, 단계) — "이전 화면으로 돌아가기"에 쓴다


# data 폴더 샘플 자료 (빈칸은 "(빈칸)"으로 보여 줌)
DATA = Path(__file__).parent / "data"


def load(name):
    return pd.read_csv(DATA / name, dtype=str).fillna("(빈칸)")


contracts = load("contracts.csv")
templates = load("templates.csv")
partners = load("partners.csv")


# PDF 에 쓰는 한글 글꼴 — 윈도우에 들어 있는 맑은 고딕
FONT = "C:/Windows/Fonts/malgun.ttf"


def wrap(draw, text, font, width):
    """글을 정해진 가로 길이에 맞춰 여러 줄로 나눈다 (줄바꿈도 그대로 살린다)"""
    lines = []
    for para in text.split("\n"):
        line = ""
        for ch in para:
            if draw.textlength(line + ch, font=font) > width:
                lines.append(line)
                line = ""
            line += ch
        lines.append(line)
    return lines


def contract_pdf(partner, amount, date, content):
    """계약서를 A4 한 장짜리 .pdf 파일 내용으로 만든다 — 새 도구 없이 Pillow 로 그림을 그려 PDF 로 저장한다"""
    page = Image.new("RGB", (1240, 1754), "white")  # A4 종이 (150dpi)
    draw = ImageDraw.Draw(page)
    title, body = ImageFont.truetype(FONT, 56), ImageFont.truetype(FONT, 30)

    draw.text((620, 160), "계  약  서", font=title, fill="black", anchor="mm")
    y = 300
    for label, value in [("거래처명 (을)", partner), ("계약 금액", amount),
                         ("계약 날짜", date), ("계약 내용", content)]:
        draw.text((140, y), label, font=body, fill="black")
        for line in wrap(draw, value, body, 1240 - 400 - 140):
            draw.text((400, y), line, font=body, fill="black")
            y += 50
        y += 30

    out = io.BytesIO()
    page.save(out, "PDF", resolution=150)
    return out.getvalue()


def file_name(partner, date):
    """계약서_거래처명_날짜 — 파일 이름으로 쓸 수 없는 글자는 _ 로 바꾼다"""
    return re.sub(r'[\\/:*?"<>|]', "_", f"계약서_{partner}_{date}") + ".pdf"


def go(screen, step=1):
    st.session_state.screen = screen
    st.session_state.step = step


def blank(value):
    """표에서 "(빈칸)"으로 읽은 칸은 입력칸에 빈 글로 채운다"""
    return "" if value == "(빈칸)" else value


def start_new():
    """"+ 계약서 새로 만들기" — 빈 입력칸으로 시작해 화면 2로 간다"""
    st.session_state.fill = {}
    st.session_state.made, st.session_state.missing = None, []
    go(SCREEN_2)


def pick_contract(row):
    """목록 항목을 고르면 — 그 계약서 내용을 담아 두고 화면 2로 간다"""
    st.session_state.fill = {"in_partner": blank(row.partner), "in_amount": blank(row.amount),
                             "in_date": blank(row.date), "in_content": blank(row.content)}
    st.session_state.made, st.session_state.missing = None, []
    go(SCREEN_2)


def next_step():
    """"다음" — 고른 양식의 본문을 계약내용 칸에 넣을 글로 담아 두고 거래처 고르기로 넘어간다 (수용 기준 7)"""
    form = st.session_state.get("form")
    if form:
        body = templates.loc[templates["name"] == form, "body"].iloc[0]
        st.session_state.setdefault("fill", {})["in_content"] = blank(body)
    go(SCREEN_2, 2)


def apply():
    """"적용" — 고른 거래처를 거래처명 칸에 넣을 글로 담아 두고 화면 3으로 간다 (수용 기준 8)"""
    partner = st.session_state.get("partner")
    if partner:
        st.session_state.setdefault("fill", {})["in_partner"] = blank(partner)
    go(SCREEN_3)


# 화면 3 입력칸 — 비어 있을 때 보여 줄 말도 함께 둔다
FIELDS = {"in_partner": "거래처명을", "in_amount": "금액을", "in_date": "날짜를", "in_content": "계약내용을"}


def make():
    """"만들기"를 누르면 — 빈 칸이 있으면 그 칸을 짚고, 다 채웠으면 계약서를 만든다"""
    missing = [word for key, word in FIELDS.items() if not st.session_state.get(key, "").strip()]
    st.session_state.missing = missing
    st.session_state.made = None if missing else tuple(st.session_state[key].strip() for key in FIELDS)


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
      /* 대화창 가로 길이 — "대화하기"와 "지난대화" 탭이 똑같은 폭으로 보이게 고정한다 */
      [data-testid="stPopoverBody"] {{ width: 400px !important; min-width: 400px !important; }}
      /* "지난대화" 탭 높이를 "대화하기" 탭 높이(말투 칸 + 대화 칸 320px + 물어볼 말 칸)에 맞춘다 */
      .st-key-past_tab {{ min-height: 464px; }}
      .copy-answer {{ font-size: 12px; padding: 2px 8px; border: 1px solid #ccc;
                      border-radius: 6px; background: white; cursor: pointer; white-space: nowrap; }}
    </style>""")
    if "chat" not in st.session_state:
        st.session_state.chat = []          # 지금까지 주고받은 말
        st.session_state.chat_last_id = None  # 이어서 대화하려고 Gemini 가 준 앞 대화 번호

    with st.container(key="chatbot"):
        with st.popover("챗봇"):
            st.markdown("**계약서 만들기 도우미**")
            talk, past = st.tabs(["대화하기", "지난대화"])
            with talk:
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

            # 가끔 보는 것 — chat_logs 표에 남은 지난 대화 목록
            with past, st.container(key="past_tab"):
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


# 첫 화면(랜딩 페이지) — streamlit run app.py 로 열면 이 화면이 먼저 뜬다
if "page" not in st.session_state:
    st.session_state.page = "landing"


def open_page(page):
    st.session_state.page = page
    if page == "app":
        go(SCREEN_1)  # 「시작하기」를 누르면 늘 화면 1(계약서 목록)부터 보인다
        st.session_state.history = []
        st.session_state.pop("last", None)


def back():
    """"이전 화면으로 돌아가기" — 누를 때마다 지나온 화면을 하나씩 거꾸로 되돌아간다"""
    if st.session_state.history:
        st.session_state.screen, st.session_state.step = st.session_state.history.pop()
        st.session_state.last = (st.session_state.screen, st.session_state.step)


if st.session_state.page == "landing":
    # 첫 화면 색 — 배경 #aeb0f8, 글자 #343534, 강조 #dc3e63
    st.html("""<style>
      .stApp { background: #aeb0f8; }
      .landing { color: #343534; text-align: center; word-break: keep-all; }
      .landing h1 { color: #dc3e63; font-size: 3.5rem; margin: 6vh 0 0.5rem; }
      .landing .intro { font-size: 1.3rem; margin-bottom: 2.5rem; }
      .landing .jobs { display: flex; gap: 1.5rem; justify-content: center; flex-wrap: wrap; }
      .landing .job { flex: 1 1 220px; max-width: 300px; padding: 1.5rem; border: 2px solid #dc3e63; border-radius: 16px; }
      .landing .job b { display: block; color: #dc3e63; font-size: 1.2rem; margin-bottom: 0.5rem; }
      .st-key-start button { background: #dc3e63; border-color: #dc3e63; color: #343534;
                             font-size: 1.2rem; padding: 0.8rem 0; margin-top: 2.5rem; }
      /* 「시작하기」 글씨 — 세 칸의 제목("계약서 목록" 등)과 같은 글꼴·크기·굵기 */
      .st-key-start button p { font-family: inherit; font-size: 1.2rem; font-weight: 700; }
    </style>""")

    # 큰 제목, 한 줄 소개, 하는 일 세 가지 — PRD.md 의 한 줄 정의와 넣을 기능 1·2·3 에서 가져왔다
    st.html("""<div class="landing">
      <h1>계약서 만들기</h1>
      <div class="intro">빈칸만 채우면 계약서가 만들어지고, 바로 내려받아 출력할 수 있습니다.</div>
      <div class="jobs">
        <div class="job"><b>계약서 목록</b>만든 계약서가 목록에 쌓여, 예전 계약서를 다시 찾아볼 수 있습니다.</div>
        <div class="job"><b>양식·거래처 고르기</b>저장해둔 양식이나 거래처 정보를 골라 입력창에 불러옵니다.</div>
        <div class="job"><b>계약서 만들기</b>거래처명·금액·날짜·계약내용을 넣고 "만들기"를 누르면 계약서가 펼쳐집니다.</div>
      </div>
    </div>""")

    # 「시작하기」를 누르면 기능 화면으로 간다
    _, mid, _ = st.columns([2, 1, 2])
    mid.button("시작하기", key="start", width="stretch", on_click=open_page, args=("app",))
    st.stop()

# 기능 화면 사이드바 맨 위 — 첫 화면으로 돌아가는 버튼
st.sidebar.button("첫 화면으로 돌아가기", width="stretch", on_click=open_page, args=("landing",))

# 사이드바 가로 길이를 줄여 가운데 화면을 넓힌다
st.html("""<style>
  [data-testid="stSidebar"] { width: 240px !important; min-width: 240px !important; max-width: 240px !important; }
</style>""")

# 이 서비스가 해 주는 일 (한 줄)
st.sidebar.write("받은 문의를 붙여 넣으면 답변 초안을 만들어 줍니다.")

# 세 화면 오가기
st.sidebar.radio("화면", [SCREEN_1, SCREEN_2, SCREEN_3], key="screen")

# 화면이 바뀌었으면 바로 전 화면을 지나온 화면 목록에 쌓는다
here = (st.session_state.screen, st.session_state.step)
if st.session_state.get("last", here) != here:
    st.session_state.history.append(st.session_state.last)
st.session_state.last = here

# 화면 고르기 바로 밑 — 바로 전 화면으로 돌아가는 버튼 (돌아갈 화면이 없으면 눌리지 않는다)
st.sidebar.button("이전 화면으로 돌아가기", width="stretch", on_click=back,
                  disabled=not st.session_state.history)

# 어느 화면에서든 오른쪽 아래에 챗봇이 보인다
chatbot()

if st.session_state.screen == SCREEN_3:
    st.warning("아직 예시 결과입니다")
    st.title("계약서 만들기")

    # 화면 1·2에서 담아 둔 내용을 입력칸에 채운다 — 입력칸을 그리기 전에 넣어야 칸에 보인다
    for key, value in st.session_state.pop("fill", {}).items():
        st.session_state[key] = value

    # 왼쪽 열은 넣는 자리, 오른쪽 열은 결과 자리 — 두 열의 가로 길이를 똑같이 둔다
    left, center = st.columns(2)

    with left:
        st.text_input("거래처명", placeholder="예: (주)한빛상사", key="in_partner")
        st.text_input("금액", placeholder="예: 5,000,000원", key="in_amount")
        st.text_input("날짜", placeholder="예: 2026.09.17", key="in_date")
        st.text_area("계약내용", placeholder="계약 조건 및 상세 내용 입력", key="in_content",
                     height=260)  # 계약내용은 길게 쓰므로 칸을 높게 둔다

    # 결과 자리 — "만들기"로 만든 계약서가 펼쳐진다 (수용 기준 1)
    made = st.session_state.get("made")
    if made:
        partner, amount, date, content = made
        center.code(
            f"""                계약서

  거래처명 (을)  : {partner}
  계약 금액      : {amount}
  계약 날짜      : {date}
  계약 내용      : {content}""",
            language=None,
        )
    else:
        center.caption("왼쪽 칸을 모두 채우고 \"만들기\"를 누르면 여기에 계약서가 펼쳐집니다.")

    # 버튼 줄 — "만들기"와 "다운로드"를 같은 높이에 나란히 둔다
    make_col, down_col = st.columns(2)
    make_col.button("만들기", width="stretch", on_click=make)

    # 빈 칸을 하나씩 짚어 보여 준다 (수용 기준 3)
    for word in st.session_state.get("missing", []):
        make_col.error(f"{word} 넣지 않았습니다")

    # 다운로드 — 계약서_거래처명_날짜.pdf 로 내려받는다 (수용 기준 4)
    # 버튼은 늘 보이게 두고, "만들기" 전에는 눌리지 않게 막아 둔다
    if not made:
        down_col.download_button("다운로드", b"", disabled=True, width="stretch")
    elif down_col.download_button("다운로드", contract_pdf(partner, amount, date, content),
                                  file_name=file_name(partner, date), mime="application/pdf",
                                  width="stretch"):
        down_col.success("다운로드 완료")

elif st.session_state.screen == SCREEN_1:
    st.warning("아직 예시 결과입니다")
    st.title("계약서 목록")

    st.button("+ 계약서 새로 만들기", width="stretch", on_click=start_new)

    # 목록 (data/contracts.csv) — 3열로 나란히 놓아 아래로 길어지지 않게 한다. 항목을 선택하면 화면 2로 간다
    cols = st.columns(3)
    for i, row in contracts.iterrows():
        cols[i % 3].button(f"{row.partner}  ·  {row.amount}  ·  {row.date}", width="stretch",
                           key=f"contract_{i}", on_click=pick_contract, args=(row,))

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
    left.button("목록으로 돌아가기", width="stretch", on_click=go, args=(SCREEN_1,))
    if step == 1:
        right.button("다음", width="stretch", on_click=next_step)
    else:
        right.button("적용", width="stretch", on_click=apply)
