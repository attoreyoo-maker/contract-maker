from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="[문의 표 연습]")

# 이 파일 옆 data 폴더의 CSV (어디서 실행해도 같은 파일을 읽음)
CSV_PATH = Path(__file__).parent / "data" / "56_practice-inquiries.csv"

st.title("문의 목록")

df = pd.read_csv(CSV_PATH)
df.columns = ["날짜", "종류", "문의 내용", "상태"]

# 종류(type) 거르기 — 처음에는 "전체"
choice = st.selectbox("종류", ["전체"] + sorted(df["종류"].unique()))
shown = df if choice == "전체" else df[df["종류"] == choice]

# 상태(status) 거르기 — 처음에는 "전체", 위 종류 거르기와 둘 다 맞는 줄만 남김
status = st.selectbox("상태", ["전체"] + sorted(df["상태"].unique()))
if status != "전체":
    shown = shown[shown["상태"] == status]

st.caption(f"보이는 줄 {len(shown)}건")
st.dataframe(shown, hide_index=True, width="stretch")
