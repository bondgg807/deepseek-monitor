"""内嵌图标资源 — 手绘闪电图标"""

from PIL import Image, ImageDraw


def create_tray_icon(size: int = 32) -> Image.Image:
    """透明底 + 正黄色闪电（像素级居中）。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    yellow = (255, 255, 0, 255)
    base = 48
    dx, dy = 4, -1
    raw = [
        (24,  6), (8,  26), (18, 26), (10, 28),
        (20, 30), (14, 46), (28, 24), (16, 24),
    ]
    pts = [((x + dx) * size / base, (y + dy) * size / base) for x, y in raw]
    draw.polygon(pts, fill=yellow)
    return img


def create_app_icon(size: int = 48) -> Image.Image:
    return create_tray_icon(size)
