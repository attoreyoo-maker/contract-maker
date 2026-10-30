"""첫 화면 히어로 영역 배경 영상(hero.mp4)을 만든다 — 글자 없이, 끝과 처음이 이어지게

계약서 만들기(PRD.md)라서, 계약서 종이를 닮은 반투명 카드들이 천천히 떠오르고
그 뒤로 #0EA5E9 빛 덩어리가 흘러 다닌다. 모든 움직임이 LOOP 초마다 처음 자리로 돌아온다.

실행 : python make_hero.py   (imageio, imageio-ffmpeg 가 있어야 mp4 로 저장된다)
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1280, 720
FPS = 30
LOOP = 8  # 초 — 이 길이마다 같은 모습으로 돌아온다
FRAMES = FPS * LOOP

# #0EA5E9 를 중심으로 한 같은 계열 색
MAIN = np.array([14, 165, 233], float)   # #0EA5E9
DARK = np.array([7, 89, 133], float)     # #075985
LIGHT = np.array([125, 211, 252], float)  # #7DD3FC
TAU = 2 * math.pi

ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)

# 빛 덩어리 — (가운데 x, y, 흔들림 x, y, 크기, 색, 세기, 위상)
BLOBS = [
    (0.25, 0.35, 0.10, 0.08, 380, LIGHT, 0.55, 0.0),
    (0.75, 0.60, 0.12, 0.10, 420, MAIN, 0.60, 0.33),
    (0.55, 0.20, 0.08, 0.06, 300, LIGHT, 0.35, 0.66),
]

# 떠오르는 계약서 카드 — (가로 자리, 크기, 한 바퀴 동안 오르는 횟수, 시작 위치, 기울기 위상, 진하기)
CARDS = [
    (0.10, 1.00, 1, 0.00, 0.1, 60),
    (0.28, 0.70, 2, 0.45, 0.5, 40),
    (0.46, 0.85, 1, 0.70, 0.9, 50),
    (0.64, 0.60, 2, 0.15, 0.3, 35),
    (0.80, 0.95, 1, 0.35, 0.7, 55),
    (0.93, 0.65, 2, 0.80, 0.2, 38),
]


def card_image(scale, alpha):
    """반투명 종이 한 장 — 글자 대신 계약서 줄을 닮은 흐린 막대만 그린다"""
    w, h = int(150 * scale), int(200 * scale)
    img = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, w, h), radius=int(14 * scale), fill=(255, 255, 255, alpha),
                        outline=(255, 255, 255, alpha + 40), width=2)
    pad = int(20 * scale)
    d.rounded_rectangle((pad + w * 0.2, pad, w - pad - w * 0.2, pad + 8 * scale),
                        radius=4, fill=(255, 255, 255, alpha + 50))
    for i in range(5):
        y = pad + (34 + i * 22) * scale
        right = w - pad - (w * 0.25 if i == 4 else 0)
        d.rounded_rectangle((pad, y, right, y + 6 * scale), radius=3, fill=(255, 255, 255, alpha + 25))
    return img


CARD_IMAGES = [card_image(s, a) for _, s, _, _, _, a in CARDS]


def frame(t):
    """t 초 때의 한 장 — t 와 t + LOOP 는 똑같은 그림이 된다"""
    p = (t % LOOP) / LOOP  # 0 ~ 1 사이 한 바퀴 진행

    # 바탕 — 어두운 하늘색에서 밝은 하늘색으로 비스듬히, 빛의 방향이 천천히 흔들린다
    angle = 0.6 + 0.25 * math.sin(TAU * p)
    g = (xs / W * math.cos(angle) + ys / H * math.sin(angle)) / (math.cos(angle) + math.sin(angle))
    rgb = DARK[None, None, :] * (1 - g[..., None]) + MAIN[None, None, :] * g[..., None]

    # 빛 덩어리 — 원과 8자 모양으로 돌다가 제자리로 온다
    for cx, cy, ax, ay, r, color, k, ph in BLOBS:
        bx = (cx + ax * math.sin(TAU * (p + ph))) * W
        by = (cy + ay * math.sin(TAU * (2 * p + ph))) * H
        glow = k * np.exp(-((xs - bx) ** 2 + (ys - by) ** 2) / (2 * r * r))
        rgb = rgb * (1 - glow[..., None]) + color[None, None, :] * glow[..., None]

    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).convert("RGBA")

    # 카드 — 아래에서 위로 떠오르다 위로 빠지면 아래에서 다시 나온다
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for (cx, _, laps, start, tilt, _), card in zip(CARDS, CARD_IMAGES):
        span = H + card.height * 2
        y = H + card.height - ((start + laps * p) % 1) * span
        x = cx * W + 18 * math.sin(TAU * (p + tilt))
        rot = card.rotate(8 * math.sin(TAU * (p + tilt)), resample=Image.BICUBIC, expand=True)
        layer.alpha_composite(rot, (int(x - rot.width / 2), int(y - rot.height / 2)))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(1.2)))
    return img.convert("RGB")


if __name__ == "__main__":
    out = Path(__file__).parent / "hero.mp4"
    if "--preview" in sys.argv:
        # 미리 보기 — 처음·중간·끝 바로 다음 장면을 그림으로 저장
        folder = Path(sys.argv[sys.argv.index("--preview") + 1])
        for name, t in [("start", 0), ("middle", LOOP / 2), ("loop", LOOP)]:
            frame(t).save(folder / f"hero_{name}.png")
        sys.exit()

    import imageio.v2 as imageio

    with imageio.get_writer(out, fps=FPS, codec="libx264", quality=8,
                            pixelformat="yuv420p", macro_block_size=16) as writer:
        for i in range(FRAMES):
            writer.append_data(np.asarray(frame(i / FPS)))
            # 한 장에 1초쯤 걸려 멈춘 것처럼 보이므로 몇 장째인지 보여 준다
            print(f"\r{i + 1}/{FRAMES} 장 만드는 중...", end="", flush=True)
        print()
    print(f"저장했습니다: {out}  ({LOOP}초, {FPS}fps, {W}x{H})")
