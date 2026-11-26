"""Draw the app icon from the SiftBase mark (renderer/index.html #i-mark): three offset pages and a highlighter stroke
on a dark rounded tile. Writes desktop/resources/icon.png (1024 px) and icon.ico (16-256 px).

    python desktop/scripts/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "resources"
N = 1024  # drawn large, scaled down for each size
TILE, SHELL_LINE = "#11141B", "#262C38"
# The mark's 24-unit viewBox shapes: (x, y, w, h, colour); pages first, the highlighter last.
MARK = [(3, 12, 13, 8, "#4A4B4F"), (5.5, 8, 13, 8, "#A3AAB7"), (8, 4, 13, 8, "#EEE9DD"), (10, 7, 9, 2.2, "#D8F25B")]


def draw():
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    inset = N * 0.04
    d.rounded_rectangle([inset, inset, N - inset, N - inset], radius=N * 0.22, fill=TILE, outline=SHELL_LINE, width=round(N * 0.012))
    # The mark spans x 3-21, y 4-20 of its viewBox; centre that 18 x 16 box in the tile at 72% of its width.
    scale = (N * 0.72) / 18
    ox = (N - 18 * scale) / 2 - 3 * scale
    oy = (N - 16 * scale) / 2 - 4 * scale
    for i, (x, y, w, h, colour) in enumerate(MARK):
        box = [ox + x * scale, oy + y * scale, ox + (x + w) * scale, oy + (y + h) * scale]
        d.rounded_rectangle(box, radius=scale * (1 if i < 3 else 0.3), fill=colour)
    return img


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    img = draw()
    img.save(OUT / "icon.png")
    img.save(OUT / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print("wrote", OUT / "icon.png", OUT / "icon.ico")
