import uuid
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from keys import get_key
from supabase import create_client

BUCKET = "photos"
TYPES = ["png", "jpg", "jpeg", "gif", "webp"]
COLS = 3  # 한 줄에 보여 줄 그림 수
URL_SECONDS = 3600  # 그림 주소를 1시간 동안 쓸 수 있게 만든다

st.set_page_config(page_title="사진 보관함")

# .env 의 SUPABASE_URL, SUPABASE_KEY(공개용 키) 로 연결
# photos 버킷은 data/photos_storage.sql 에서 공개용 키로 올리기·목록 보기를 열어 두었다
load_dotenv()
url = get_key("SUPABASE_URL")
key = get_key("SUPABASE_KEY")
if not url or not key:
    st.error(".env 에 SUPABASE_URL 과 SUPABASE_KEY 를 넣어 주세요.")
    st.stop()

bucket = create_client(url, key).storage.from_(BUCKET)

st.title("🖼️ 사진 보관함")

# 올리기를 누른 뒤 다시 그려진 화면에 결과 알림을 한 번 보여 준다
if "notice" in st.session_state:
    st.success(st.session_state.pop("notice"))

# 그림 올리기 — 올린 뒤 고르기 칸을 비우려고 key 에 번호를 붙인다
st.subheader("올리기")
st.session_state.setdefault("version", 0)
files = st.file_uploader(
    "올릴 그림 고르기", type=TYPES, accept_multiple_files=True,
    key=f"uploader_{st.session_state.version}",
)
if st.button("올리기", type="primary"):
    if not files:
        st.warning("올릴 그림을 고르지 않았습니다.")
    else:
        try:
            for f in files:
                # Storage 는 한글 파일 이름을 받지 않으므로, 올린 시각 + 짧은 무작위 글자로 이름을 새로 짓는다
                ext = f.name.rsplit(".", 1)[-1].lower()
                name = f"{datetime.now():%Y%m%d-%H%M%S}_{uuid.uuid4().hex[:6]}.{ext}"
                bucket.upload(name, f.getvalue(), {"content-type": f.type})
        except Exception as e:
            st.error(f"올리지 못했습니다: {e}")
        else:
            st.session_state.notice = f"그림 {len(files)}장을 올렸습니다."
            st.session_state.version += 1
            st.rerun()

# 올라와 있는 그림 — 최근에 올린 것이 위로
try:
    items = bucket.list("", {"limit": 1000, "sortBy": {"column": "created_at", "order": "desc"}})
except Exception as e:
    st.error(f"photos 버킷을 읽지 못했습니다. data/photos_storage.sql 을 먼저 실행했는지 확인해 주세요. ({e})")
    st.stop()

# 폴더나 빈 폴더 표시용 파일(.emptyFolderPlaceholder)은 빼고 그림만 남긴다
photos = [i for i in items if i.get("id") and not i["name"].startswith(".")]

st.subheader(f"올라온 그림 : {len(photos)}장")
if not photos:
    st.caption("아직 올라온 그림이 없습니다.")
    st.stop()

# 공개 버킷이 아니어도 보이도록, 잠시 쓸 수 있는 주소를 한꺼번에 받아 온다
signed = bucket.create_signed_urls([p["name"] for p in photos], URL_SECONDS)
urls = {s["path"]: s["signedURL"] for s in signed}

cols = st.columns(COLS)
for n, p in enumerate(photos):
    with cols[n % COLS]:
        st.image(urls[p["name"]], width="stretch")
        # Storage 는 세계 표준시(UTC)로 주므로 내 컴퓨터 시각으로 바꿔 보여 준다
        uploaded = datetime.fromisoformat(p["created_at"].replace("Z", "+00:00")).astimezone()
        st.caption(f"{uploaded:%Y-%m-%d %H:%M} · {p['name']}")
