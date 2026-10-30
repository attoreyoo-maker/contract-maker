from urllib.parse import quote

import altair as alt
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from keys import get_key

KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
NAVER_SEARCH_URL = "https://map.naver.com/p/search/"
CENTER_NAME = "전주신시가지"
FOOD_CODE = "FD6"  # 카카오 카테고리 그룹 코드: 음식점
PAGE_SIZE = 15  # 한 번에 받을 수 있는 최대 개수
MAX_PAGE = 3  # 카카오는 검색어당 최대 45건(15건 x 3쪽)까지만 돌려준다
TIMEOUT = 10  # 초

# 찾을 음식 고르기: 화면에 보이는 이름 → 카카오에 보낼 검색어
# (음식점(FD6)으로만 거르므로 카페는 넣지 않는다. 카페는 카카오에서 따로 CE7 로 나뉜다)
FOODS = {
    "전체 (맛집)": "맛집",
    "한식": "한식",
    "중식": "중식",
    "일식": "일식",
    "양식": "양식",
    "분식": "분식",
    "국밥": "국밥",
    "고기": "고기",
    "치킨": "치킨",
    "피자": "피자",
}
CUSTOM_FOOD = "직접 입력"
RADII = [100, 200, 300, 500, 700, 1000, 1500, 2000, 3000, 5000]  # 미터

SORTS = {
    "거리 가까운 순": ("거리(m)", True),
    "거리 먼 순": ("거리(m)", False),
    "이름 가나다순": ("이름", True),
    "종류 가나다순": ("종류", True),
}

st.set_page_config(page_title="맛집 대시보드", layout="wide")

# 키 값은 화면에 보이지 않고, 채워져 있는지만 확인한다
load_dotenv()
api_key = get_key("KAKAO_REST_API_KEY", "").strip()

st.title("맛집 대시보드")

if not api_key:
    st.error("KAKAO_REST_API_KEY 가 비어 있습니다. .env 에 넣어 주세요.")
    st.stop()

HEADERS = {"Authorization": f"KakaoAK {api_key}"}


def call_kakao(params):
    res = requests.get(KEYWORD_URL, headers=HEADERS, params=params, timeout=TIMEOUT)
    res.raise_for_status()
    return res.json()


def find_center(place):
    """기준 장소를 키워드로 찾아 카카오가 돌려준 첫 결과의 좌표(경도 x, 위도 y)·이름·주소를 얻는다."""
    docs = call_kakao({"query": place, "size": 1})["documents"]
    if not docs:
        raise ValueError(f"'{place}' 위치를 카카오에서 찾지 못했습니다. 역 이름이나 동네 이름을 바꿔 보세요.")
    d = docs[0]
    return d["x"], d["y"], d["place_name"], d["road_address_name"] or d["address_name"]


def search_restaurants(place, query, radius):
    x, y, found_name, address = find_center(place)
    rows = []
    for page in range(1, MAX_PAGE + 1):
        data = call_kakao({
            "query": query,
            "category_group_code": FOOD_CODE,
            "x": x,
            "y": y,
            "radius": radius,
            "sort": "distance",
            "page": page,
            "size": PAGE_SIZE,
        })
        for d in data["documents"]:
            rows.append({
                "이름": d["place_name"],
                # "음식점 > 한식 > 국밥" 에서 두 번째 마디(한식 등)를 큰 종류로 쓴다
                "종류": (d["category_name"].split(" > ") + ["기타"])[1],
                "세부 종류": d["category_name"].split(" > ")[-1],
                "거리(m)": int(d["distance"]) if d.get("distance") else None,
                "전화": d["phone"],
                "주소": d["road_address_name"] or d["address_name"],
                "카카오맵": d["place_url"],
            })
        if data["meta"]["is_end"]:
            break
    return pd.DataFrame(rows), found_name, address


# 내 조건으로 찾기: 값을 바꿔도 검색 버튼을 누르기 전에는 카카오를 부르지 않는다
with st.container(border=True):
    st.subheader("내 조건으로 찾기")
    c0, c1, c2 = st.columns(3)
    place = c0.text_input("기준 장소", value=CENTER_NAME, help="역이나 동네 이름. 예: 전주역, 객사, 효자동")
    food = c1.selectbox("찾을 음식", list(FOODS) + [CUSTOM_FOOD])
    if food == CUSTOM_FOOD:
        query = c1.text_input("음식 이름", placeholder="예: 비빔밥, 콩나물국밥")
    else:
        query = FOODS[food]
    radius = c2.select_slider("반경", options=RADII, value=500, format_func=lambda m: f"{m}m" if m < 1000 else f"{m / 1000:g}km")
    clicked = st.button("검색", type="primary")

if clicked:
    if not place.strip():
        st.warning("기준 장소를 넣지 않았습니다.")
    elif not query.strip():
        st.warning("음식 이름을 넣지 않았습니다.")
    else:
        try:
            with st.spinner("카카오에서 검색하는 중..."):
                df, found_name, address = search_restaurants(place.strip(), query.strip(), radius)
            st.session_state["result"] = (df, found_name, address, query.strip(), radius)
        except requests.HTTPError as e:
            code = e.response.status_code
            hint = " (키가 올바른지, 카카오 로그인·로컬 API 사용이 켜져 있는지 확인하세요)" if code in (401, 403) else ""
            st.error(f"카카오 요청이 실패했습니다: HTTP {code}{hint}")
        except (requests.RequestException, ValueError) as e:
            st.error(f"카카오를 부르지 못했습니다: {e}")

if "result" not in st.session_state:
    st.info("기준 장소, 찾을 음식, 반경을 정하고 '검색' 버튼을 눌러 주세요.")
    st.stop()

df, found_name, address, used_query, used_radius = st.session_state["result"]
# 기준 장소는 카카오가 돌려준 이름·주소를 그대로 보여 준다
st.success(f"**기준 장소 (카카오에서 찾은 곳)** : {found_name} — {address}")
st.caption(f"찾을 음식 '{used_query}' · 반경 {used_radius}m 안의 음식점")

# 네이버 지도 검색 주소: 가게 이름 + 도로명 주소("주소" 칸, 도로명이 없으면 지번 주소). 카카오는 부르지 않는다
if not df.empty:
    df = df.assign(네이버지도=NAVER_SEARCH_URL + (df["이름"] + " " + df["주소"]).map(quote))

if df.empty:
    st.warning("조건에 맞는 음식점이 없습니다. 반경을 넓히거나 검색어를 바꿔 보세요.")
    st.stop()
if len(df) >= PAGE_SIZE * MAX_PAGE:
    st.caption(f"카카오는 한 번에 최대 {PAGE_SIZE * MAX_PAGE}건까지만 알려 줍니다. 더 보려면 반경을 줄이거나 검색어를 좁혀 보세요.")

# 이미 받은 결과를 거르고 정렬한다 (카카오를 다시 부르지 않음)
f1, f2 = st.columns([3, 2])
kinds = sorted(df["종류"].unique())
picked = f1.multiselect("종류", kinds, default=kinds)
sort_label = f2.selectbox("정렬", list(SORTS))

col, asc = SORTS[sort_label]
view = df[df["종류"].isin(picked)].sort_values(col, ascending=asc, kind="stable").reset_index(drop=True)

m1, m2, m3 = st.columns(3)
m1.metric("음식점 수", f"{len(view)}곳")
m2.metric("가장 가까운 곳", f"{int(view['거리(m)'].min())}m" if len(view) else "-")
m3.metric("평균 거리", f"{int(view['거리(m)'].mean())}m" if len(view) else "-")

# 맛집 뽑기: 지금 표에 보이는 가게(view) 안에서만 고른다. 카카오는 부르지 않는다
if st.button("맛집 뽑기", disabled=view.empty):
    st.session_state["pick_url"] = view.sample(1).iloc[0]["카카오맵"]

pick = view[view["카카오맵"] == st.session_state.get("pick_url")]
if not pick.empty:
    p = pick.iloc[0]
    with st.container(border=True):
        st.caption("오늘의 맛집")
        st.markdown(f"# {p['이름']}")
        st.markdown(f"### {p['종류']} · {p['거리(m)']}m")
        st.link_button("카카오맵에서 보기", p["카카오맵"])

tab_table, tab_chart = st.tabs(["목록", "차트"])

with tab_table:
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        # 표의 링크는 누르면 새 탭에서 열린다
        column_config={
            "카카오맵": st.column_config.LinkColumn("카카오맵", display_text="열기"),
            "네이버지도": st.column_config.LinkColumn("네이버지도", display_text="열기"),
        },
    )

with tab_chart:
    if view.empty:
        st.info("고른 종류가 없습니다.")
    else:
        BAR = "#3b6ea5"
        left, right = st.columns(2)

        by_kind = view.groupby("종류").size().reset_index(name="곳 수")
        left.subheader("종류별 음식점 수")
        left.altair_chart(
            alt.Chart(by_kind).mark_bar(color=BAR).encode(
                x=alt.X("곳 수:Q", title="곳"),
                y=alt.Y("종류:N", sort="-x", title=None),
                tooltip=["종류", "곳 수"],
            ),
            use_container_width=True,
        )

        right.subheader("거리 분포")
        right.altair_chart(
            alt.Chart(view).mark_bar(color=BAR).encode(
                x=alt.X("거리(m):Q", bin=alt.Bin(step=100), title="기준 장소에서 거리 (m)"),
                y=alt.Y("count():Q", title="곳"),
            ),
            use_container_width=True,
        )

        by_detail = view.groupby("세부 종류").size().reset_index(name="곳 수").nlargest(10, "곳 수")
        st.subheader("세부 종류 상위 10")
        st.altair_chart(
            alt.Chart(by_detail).mark_bar(color=BAR).encode(
                x=alt.X("곳 수:Q", title="곳"),
                y=alt.Y("세부 종류:N", sort="-x", title=None),
                tooltip=["세부 종류", "곳 수"],
            ),
            use_container_width=True,
        )
