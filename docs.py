import base64
import uuid
from datetime import datetime, timedelta

import streamlit as st
from dotenv import load_dotenv
from keys import get_key
from supabase import create_client

BUCKET = "docs"
LINK_SECONDS = 60  # 내려받기 링크는 60초 동안만 열린다

st.set_page_config(page_title="문서 보관함")

# .env 의 SUPABASE_URL, SUPABASE_KEY(공개용 키) 로 연결
# docs 버킷은 data/docs_storage.sql 에서 공개용 키로 올리기·목록 보기를 열어 두었다
load_dotenv()
url = get_key("SUPABASE_URL")
key = get_key("SUPABASE_KEY")
if not url or not key:
    st.error(".env 에 SUPABASE_URL 과 SUPABASE_KEY 를 넣어 주세요.")
    st.stop()

bucket = create_client(url, key).storage.from_(BUCKET)


# Storage 는 한글 파일 이름을 받지 않으므로, 원래 이름을 영문·숫자로 바꿔 저장 이름 끝에 붙인다
# 저장 이름 모양 : 올린시각_무작위6글자_원래이름(바꾼 것)
def to_key(original):
    encoded = base64.urlsafe_b64encode(original.encode()).decode().rstrip("=")
    return f"{datetime.now():%Y%m%d-%H%M%S}_{uuid.uuid4().hex[:6]}_{encoded}"


def to_original(key_name):
    """저장 이름에서 원래 이름을 되살린다. 이 화면으로 올리지 않은 파일은 저장 이름을 그대로 쓴다."""
    try:
        encoded = key_name.split("_", 2)[2]
        return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    except (IndexError, ValueError):
        return key_name


def size_text(n):
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f}MB"
    return f"{max(n / 1024, 0.1):.1f}KB"


st.title("📁 문서 보관함")

# 올리기를 누른 뒤 다시 그려진 화면에 결과 알림을 한 번 보여 준다
if "notice" in st.session_state:
    st.success(st.session_state.pop("notice"))

# 문서 올리기 — 올린 뒤 고르기 칸을 비우려고 key 에 번호를 붙인다
st.subheader("올리기")
st.session_state.setdefault("version", 0)
files = st.file_uploader(
    "올릴 문서 고르기", accept_multiple_files=True,
    key=f"uploader_{st.session_state.version}",
)
if st.button("올리기", type="primary"):
    if not files:
        st.warning("올릴 문서를 고르지 않았습니다.")
    else:
        try:
            for f in files:
                bucket.upload(to_key(f.name), f.getvalue(), {"content-type": f.type or "application/octet-stream"})
        except Exception as e:
            st.error(f"올리지 못했습니다: {e}")
        else:
            st.session_state.notice = f"문서 {len(files)}개를 올렸습니다."
            st.session_state.version += 1
            st.rerun()

# 올라와 있는 문서 — 최근에 올린 것이 위로
try:
    items = bucket.list("", {"limit": 1000, "sortBy": {"column": "created_at", "order": "desc"}})
except Exception as e:
    st.error(f"docs 버킷을 읽지 못했습니다. data/docs_storage.sql 을 먼저 실행했는지 확인해 주세요. ({e})")
    st.stop()

# 폴더나 빈 폴더 표시용 파일(.emptyFolderPlaceholder)은 빼고 문서만 남긴다
docs = [i for i in items if i.get("id") and not i["name"].startswith(".")]

st.subheader(f"올라온 문서 : {len(docs)}개")
if not docs:
    st.caption("아직 올라온 문서가 없습니다.")
    st.stop()

until = datetime.now() + timedelta(seconds=LINK_SECONDS)
st.caption(f"내려받기 링크는 {until:%H:%M:%S} 까지만 열립니다. 그 뒤에는 화면을 새로 고쳐 새 링크를 받으세요.")

for d in docs:
    original = to_original(d["name"])
    # 링크마다 원래 이름을 붙여, 내려받은 파일도 원래 이름으로 저장되게 한다
    link = bucket.create_signed_url(d["name"], LINK_SECONDS, {"download": original})["signedURL"]
    # Storage 는 세계 표준시(UTC)로 주므로 내 컴퓨터 시각으로 바꿔 보여 준다
    uploaded = datetime.fromisoformat(d["created_at"].replace("Z", "+00:00")).astimezone()
    size = (d.get("metadata") or {}).get("size", 0)

    with st.container(border=True):
        left, right = st.columns([4, 1], vertical_alignment="center")
        left.markdown(f"**{original}**")
        left.caption(f"{uploaded:%Y-%m-%d %H:%M} · {size_text(size)}")
        right.link_button("내려받기", link, width="stretch")
        # 기한 있는 주소(signed URL)를 그대로 링크로 보여 준다 — 누르면 내려받아진다
        st.markdown(f"[{link}]({link})")
