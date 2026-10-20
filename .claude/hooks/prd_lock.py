"""PRD 자물쇠: AI가 루트의 PRD.md 를 고치거나 새로 쓰려 하면 막는다."""
import json
import os
import re
import subprocess
import sys

LOCKED = os.path.normcase(r"C:\Users\user\Desktop\my_service\PRD.md")
TITLE = "PRD 자물쇠"
MESSAGE = "[기획서는 직접 고쳐 주세요]"
REASON = "PRD.md 는 잠겨 있으니 고치지 말고 바꿀 내용을 제안만 하라"


def show_dialog():
    import tkinter as tk
    import winsound

    root = tk.Tk()
    root.title(TITLE)
    root.attributes("-topmost", True)
    root.resizable(False, False)
    tk.Label(root, text=MESSAGE, font=("Malgun Gothic", 14), padx=40, pady=24).pack()
    tk.Button(root, text="확인", width=10, command=root.destroy).pack(pady=(0, 16))
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.lift()
    root.focus_force()
    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    root.mainloop()


def launch_dialog():
    # 창을 따로 떨어진 프로세스로 띄워, 창이 떠 있는 동안 훅이 멈추지 않게 한다
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    subprocess.Popen(
        [exe, os.path.abspath(__file__), "--dialog"],
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


PRD_NAME = re.compile(r"prd\.md", re.IGNORECASE)
# 출력 방향 바꾸기(> 나 >>)로 PRD.md 에 쓰는 것
REDIRECT_TO_PRD = re.compile(r"\d?>>?\|?\s*[\"']?[^\s\"';|&]*prd\.md", re.IGNORECASE)
# PRD.md 를 읽기만 하는 명령 (이 명령들은 PRD.md 를 바꾸지 못한다)
READ_ONLY = {
    "cat", "head", "tail", "less", "more", "grep", "egrep", "fgrep", "rg",
    "wc", "diff", "file", "stat", "ls", "dir", "type", "echo", "sort", "uniq",
    "findstr", "gc", "get-content", "select-string", "sls", "get-item",
    "get-childitem", "gci", "test-path", "get-filehash", "measure-object",
    "write-output", "write-host",
}


def split_segments(command):
    """따옴표 밖의 ; & | 줄바꿈 으로 명령을 나눈다."""
    segments, cur, quote = [], [], None
    for ch in command:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch in ";&|\n":
            segments.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    segments.append("".join(cur))
    return segments


def strip_quoted(text):
    return re.sub(r"\"[^\"]*\"|'[^']*'", " ", text)


def first_word(segment):
    words = segment.strip().lstrip("(&.{ ").split()
    # VAR=값 이나 $변수 = 처럼 앞에 붙은 대입은 건너뛴다
    while words and ("=" in words[0] and not words[0].startswith("-") or words[0].startswith("$")):
        words = words[1:]
        if words and words[0] == "=":
            words = words[1:]
    if not words:
        return ""
    word = words[0].strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return word[:-4] if word.endswith(".exe") else word


def command_writes_prd(command):
    if not PRD_NAME.search(command):
        return False
    # > 는 따옴표 밖에서만 출력 방향 바꾸기이므로, 따옴표 안을 지우고 본다.
    # 단, > "PRD.md" 처럼 따옴표로 감싼 대상도 잡도록 원래 명령에서도 본다
    unquoted = strip_quoted(command)
    if REDIRECT_TO_PRD.search(command) and re.search(r">", unquoted):
        return True
    for segment in split_segments(command):
        if not PRD_NAME.search(segment):
            continue
        if first_word(segment) not in READ_ONLY:
            return True
    return False


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command")
    if command is not None:
        # Bash·PowerShell 명령: PRD.md 를 바꿀 수 있는 명령만 막는다
        if not command_writes_prd(command):
            return
    else:
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not path:
            return
        if not os.path.isabs(path):
            path = os.path.join(data.get("cwd") or os.getcwd(), path)
        if os.path.normcase(os.path.abspath(path)) != LOCKED:
            return

    launch_dialog()
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASON,
        }
    }))


if __name__ == "__main__":
    if "--dialog" in sys.argv:
        show_dialog()
    else:
        main()
