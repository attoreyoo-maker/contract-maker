# 이 파일이 무엇을 하는지 적은 설명 글
"""할 일 검사: AI가 루트의 tasks.md 에 수용 기준 번호 없는 할 일 줄을 쓰려 하면 막는다."""
# Claude Code 가 보내 준 정보(JSON 글)를 읽고, 답을 JSON 글로 쓰는 도구를 불러온다
import json
# 파일 경로를 다루는 도구를 불러온다
import os
# 글자 모양(정규식)으로 줄을 가르는 도구를 불러온다
import re
# 경고창을 다른 프로그램으로 따로 띄우는 도구를 불러온다
import subprocess
# 지금 실행 중인 파이썬 정보와 입력·출력을 다루는 도구를 불러온다
import sys

# 지킬 파일: 이 폴더 맨 위의 tasks.md (대소문자 차이를 없앤 경로)
TARGET = os.path.normcase(r"C:\Users\user\Desktop\my_service\tasks.md")
# 경고창 제목줄에 보일 글
TITLE = "할 일 검사"
# 경고창 가운데에 보일 글
MESSAGE = "[할 일마다 수용 기준 번호를 달아 주세요]"
# 막을 때 Claude 에게 알려 줄 까닭
REASON = "tasks.md 의 할 일 줄(- [ ] 로 시작)에 '(수용 기준 번호)' 또는 '(질문 필요' 가 없다"

# 할 일 줄 모양: 줄 앞(띄어쓰기는 괜찮음)이 "- [ ] " 로 시작하는 줄
TASK_LINE = re.compile(r"^\s*- \[ \] ")
# (수용 기준 1) 처럼 번호를 달았거나, 근거가 없어 (질문 필요 ...) 로 표시한 줄은 통과
LINKED = re.compile(r"\(수용 기준 \d|\(질문 필요")


# 경고창을 화면에 띄우는 일
def show_dialog():
    # 창을 만드는 도구를 불러온다
    import tkinter as tk
    # 알림 소리를 내는 도구를 불러온다
    import winsound

    # 새 창을 하나 만든다
    root = tk.Tk()
    # 창 제목줄에 제목을 적는다
    root.title(TITLE)
    # 창을 다른 창들보다 늘 맨 앞에 둔다
    root.attributes("-topmost", True)
    # 창 크기를 늘이거나 줄이지 못하게 한다
    root.resizable(False, False)
    # 경고 글을 맑은 고딕 14 크기로 여백을 두고 창에 넣는다
    tk.Label(root, text=MESSAGE, font=("Malgun Gothic", 14), padx=40, pady=24).pack()
    # "확인" 버튼을 넣고, 누르면 창이 닫히게 한다
    tk.Button(root, text="확인", width=10, command=root.destroy).pack(pady=(0, 16))
    # 창 크기를 재기 위해 지금까지 넣은 것을 먼저 계산해 둔다
    root.update_idletasks()
    # 창의 너비와 높이를 잰다
    w, h = root.winfo_width(), root.winfo_height()
    # 화면 가운데에 오도록 창의 가로 위치를 정한다
    x = (root.winfo_screenwidth() - w) // 2
    # 화면 가운데에 오도록 창의 세로 위치를 정한다
    y = (root.winfo_screenheight() - h) // 2
    # 정한 크기와 위치로 창을 옮긴다
    root.geometry(f"{w}x{h}+{x}+{y}")
    # 창을 다른 창들 위로 올린다
    root.lift()
    # 키보드 입력을 이 창으로 가져온다
    root.focus_force()
    # 경고 소리를 한 번 낸다
    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    # "확인"을 눌러 닫을 때까지 창을 띄워 둔다
    root.mainloop()


# 경고창을 띄우는 프로그램을 따로 실행하는 일
def launch_dialog():
    # 창을 따로 떨어진 프로세스로 띄워, 창이 떠 있는 동안 훅이 멈추지 않게 한다
    # 지금 이 스크립트를 돌리는 파이썬 실행 파일 위치
    exe = sys.executable
    # 같은 폴더의 pythonw.exe (검은 명령창 없이 도는 파이썬) 위치
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    # pythonw.exe 가 있으면
    if os.path.exists(pythonw):
        # 그것으로 실행해 검은 명령창이 안 뜨게 한다
        exe = pythonw
    # 새 프로그램을 이 훅과 떨어뜨리고, 명령창 없이 띄우는 설정 값
    flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    # 새 프로그램을 실행한다
    subprocess.Popen(
        # 이 스크립트 자신을 "--dialog" 를 붙여 실행 → 경고창만 띄우게 된다
        [exe, os.path.abspath(__file__), "--dialog"],
        # 위에서 정한 떨어뜨리기 설정을 쓴다
        creationflags=flags,
        # 새 프로그램에는 입력을 주지 않는다
        stdin=subprocess.DEVNULL,
        # 새 프로그램의 출력은 버린다
        stdout=subprocess.DEVNULL,
        # 새 프로그램의 오류 출력도 버린다
        stderr=subprocess.DEVNULL,
        # 이 훅이 연 파일들을 새 프로그램에 넘기지 않는다
        close_fds=True,
    # 실행 명령 끝
    )


# 지금 저장되어 있는 tasks.md 글을 읽는 일
def read_current():
    # 읽다가 문제가 생기면 아래 except 로 간다
    try:
        # tasks.md 를 한글이 깨지지 않게(utf-8) 연다
        with open(TARGET, encoding="utf-8") as f:
            # 파일 글 전체를 돌려준다
            return f.read()
    # 파일이 없거나 열 수 없으면
    except OSError:
        # 빈 글을 돌려준다
        return ""


# Edit 도구가 고친 뒤의 글을 미리 만들어 보는 일
def apply_edit(text, old, new, replace_all=False):
    # 바꿀 글(old)이 지금 글 안에 없으면
    if old not in text:
        return None  # 바꿀 글이 없으면 Edit 도구가 스스로 실패하므로 판정하지 않는다
    # 모두 바꾸기면 전부, 아니면 처음 한 곳만 바꾼 글을 돌려준다
    return text.replace(old, new) if replace_all else text.replace(old, new, 1)


# 도구 종류에 따라 고친 뒤의 tasks.md 글을 만드는 일
def content_after(tool_name, tool_input):
    """고친 뒤의 tasks.md 전체 글을 미리 만들어 본다."""
    # 파일을 통째로 새로 쓰는 Write 도구이면
    if tool_name == "Write":
        # 새로 쓸 글 전체가 곧 고친 뒤의 글이다
        return tool_input.get("content", "")
    # 일부를 바꾸는 Edit 도구이면
    if tool_name == "Edit":
        # 지금 글에 바꾸기를 적용해 본 결과를 돌려준다
        return apply_edit(
            # 지금 저장된 tasks.md 글
            read_current(),
            # 바꿀 글
            tool_input.get("old_string", ""),
            # 새 글
            tool_input.get("new_string", ""),
            # 모두 바꾸기인지
            tool_input.get("replace_all", False),
        # apply_edit 부르기 끝
        )
    # 그 밖의 도구는 판정하지 않는다
    return None


# 번호가 빠진 할 일 줄을 찾는 일
def unlinked_lines(text):
    """수용 기준 번호도 (질문 필요 표시도 없는 할 일 줄의 줄 번호."""
    # 찾은 줄 번호들을 목록으로 돌려준다
    return [
        # 글을 한 줄씩, 1번부터 줄 번호를 붙여 보면서
        n for n, line in enumerate(text.splitlines(), 1)
        # 할 일 줄인데 수용 기준 번호도 (질문 필요 도 없는 줄만 고른다
        if TASK_LINE.match(line) and not LINKED.search(line)
    # 목록 끝
    ]


# 훅이 실행될 때 하는 일 전체
def main():
    # Claude Code 가 보낸 정보를 한글이 깨지지 않게 읽어 JSON 으로 푼다
    data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    # 도구에 넘긴 값들(파일 경로, 글 등)을 꺼낸다
    tool_input = data.get("tool_input") or {}
    # 쓰거나 고칠 파일 경로를 꺼낸다
    path = tool_input.get("file_path")
    # 파일 경로가 없으면
    if not path:
        # 검사하지 않고 끝낸다 (통과)
        return
    # 경로가 "tasks.md" 처럼 짧게 적혀 있으면
    if not os.path.isabs(path):
        # 작업 폴더를 붙여 전체 경로로 만든다
        path = os.path.join(data.get("cwd") or os.getcwd(), path)
    # 그 파일이 지킬 tasks.md 가 아니면
    if os.path.normcase(os.path.abspath(path)) != TARGET:
        # 검사하지 않고 끝낸다 (통과)
        return

    # 고친 뒤의 tasks.md 글을 미리 만든다
    text = content_after(data.get("tool_name"), tool_input)
    # 미리 만들 수 없으면
    if text is None:
        # 검사하지 않고 끝낸다 (통과)
        return
    # 번호가 빠진 할 일 줄을 찾는다
    bad = unlinked_lines(text)
    # 하나도 없으면
    if not bad:
        # 끝낸다 (통과)
        return

    # 걸렸으니 경고창을 띄운다
    launch_dialog()
    # 걸린 줄 번호들을 "10, 12" 처럼 한 줄 글로 만든다
    lines = ", ".join(str(n) for n in bad)
    # Claude Code 에게 "이 쓰기를 막아라" 라는 답을 JSON 글로 보낸다
    print(json.dumps({
        # 훅이 내놓는 결과 묶음
        "hookSpecificOutput": {
            # 도구를 쓰기 직전에 실행된 훅이라는 표시
            "hookEventName": "PreToolUse",
            # 결정: 막는다
            "permissionDecision": "deny",
            # 막는 까닭과 걸린 줄 번호
            "permissionDecisionReason": f"{REASON} (고친 뒤 {lines}번째 줄)",
        # 결과 묶음 끝
        }
    # 답 보내기 끝
    }))


# 이 파일을 직접 실행했을 때만 아래를 한다
if __name__ == "__main__":
    # "--dialog" 를 붙여 실행했으면 (경고창용 실행)
    if "--dialog" in sys.argv:
        # 경고창만 띄운다
        show_dialog()
    # 그냥 실행했으면 (훅으로 실행)
    else:
        # 검사를 한다
        main()
