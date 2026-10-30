import os

import streamlit as st


def get_key(name, default=None):
    """키를 이름으로 읽는다 — 내 컴퓨터에서는 .env, 올린 곳(Streamlit Community Cloud)에서는 Secrets 에서 같은 이름으로 찾는다"""
    value = os.getenv(name)
    if value:
        return value
    try:
        value = st.secrets.get(name)
    except Exception:  # 내 컴퓨터에 Secrets 파일이 없으면 오류가 나므로 없는 것으로 친다
        value = None
    return str(value) if value else default
