import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from keys import get_key
from supabase import create_client

TABLE = "subscriptions"
COLUMNS = ["id", "name", "category", "monthly_fee", "last_used"]

st.set_page_config(page_title="구독 정리함")

# .env 의 SUPABASE_URL, SUPABASE_KEY(공개용 키) 로 연결
# subscriptions 표는 data/76_subscriptions.sql 에서 공개용 키로 읽기·넣기·고치기·지우기를 열어 두었다
load_dotenv()
url = get_key("SUPABASE_URL")
key = get_key("SUPABASE_KEY")
if not url or not key:
    st.error(".env 에 SUPABASE_URL 과 SUPABASE_KEY 를 넣어 주세요.")
    st.stop()

supabase = create_client(url, key)

st.title("💳 구독 정리함")
st.caption("다달이 돈이 나가는 것을 한곳에서 보고, 더하고, 고치고, 지웁니다.")

# 버튼을 누른 뒤 다시 그려진 화면에 결과 알림을 한 번 보여 준다
if "notice" in st.session_state:
    st.success(st.session_state.pop("notice"))

try:
    # 한 달 요금이 비싼 것부터, 요금이 같으면 먼저 넣은 것부터
    rows = supabase.table(TABLE).select("*").order("monthly_fee", desc=True).order("id").execute().data
except Exception as e:
    st.error(f"subscriptions 표를 읽지 못했습니다. data/76_subscriptions.sql 을 먼저 실행했는지 확인해 주세요. ({e})")
    st.stop()


def done(message):
    st.session_state.notice = message
    st.rerun()


# 위쪽 합계
with st.container(border=True):
    left, right = st.columns(2)
    left.metric("구독 수", f"{len(rows)}개")
    right.metric("한 달 합계", f"{sum(r['monthly_fee'] for r in rows):,}원")

# 구독 목록 — 보기만 하는 표
st.subheader("구독 목록")
if not rows:
    st.caption("아직 구독이 없습니다. 아래 \"더하기\"에서 넣어 주세요.")
else:
    table = pd.DataFrame(rows, columns=COLUMNS)
    table["monthly_fee"] = table["monthly_fee"].map(lambda v: f"{v:,}원")
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={
            "id": "id",
            "name": "이름",
            "category": "종류",
            "monthly_fee": "한 달 요금",
            "last_used": "마지막으로 쓴 날",
        },
    )

by_id = {r["id"]: r for r in rows}


def label(sub_id):
    r = by_id[sub_id]
    return f"{r['id']} · {r['name']} ({r['monthly_fee']:,}원)"


# 고치기 — 구독을 고르고 새 한 달 요금을 넣어 고친다
st.subheader("✏️ 고치기")
if rows:
    with st.container(border=True):
        edit_id = st.selectbox("고칠 구독", list(by_id), format_func=label, key="edit_id")
        with st.form("edit"):
            # 고른 구독이 바뀌면 지금 요금이 새로 채워지도록 key 에 id 를 넣는다
            new_fee = st.number_input(
                "새 한 달 요금", min_value=0, step=100,
                value=by_id[edit_id]["monthly_fee"], key=f"fee_{edit_id}",
            )
            if st.form_submit_button("고치기"):
                supabase.table(TABLE).update({"monthly_fee": int(new_fee)}).eq("id", edit_id).execute()
                done(f"'{by_id[edit_id]['name']}' 의 한 달 요금을 {int(new_fee):,}원으로 고쳤습니다.")
else:
    st.caption("고칠 구독이 없습니다.")

# 지우기 — 구독을 고르고 지운다
st.subheader("🗑️ 지우기")
if rows:
    with st.container(border=True):
        delete_id = st.selectbox("지울 구독", list(by_id), format_func=label, key="delete_id")
        if st.button("지우기"):
            supabase.table(TABLE).delete().eq("id", delete_id).execute()
            done(f"'{by_id[delete_id]['name']}' 을(를) 지웠습니다.")
else:
    st.caption("지울 구독이 없습니다.")

# 더하기 — 새 구독을 한 줄 넣는다
st.subheader("➕ 더하기")
with st.form("add", clear_on_submit=True, border=True):
    name = st.text_input("이름")
    category = st.text_input("종류")
    fee = st.number_input("한 달 요금", min_value=0, step=100, value=0)
    last_used = st.date_input("마지막으로 쓴 날", value=None)
    if st.form_submit_button("더하기"):
        if not name.strip():
            st.warning("이름을 넣지 않았습니다.")
        elif not category.strip():
            st.warning("종류를 넣지 않았습니다.")
        else:
            supabase.table(TABLE).insert({
                "name": name.strip(),
                "category": category.strip(),
                "monthly_fee": int(fee),
                "last_used": last_used.isoformat() if last_used else None,
            }).execute()
            done(f"'{name.strip()}' 을(를) 더했습니다.")
