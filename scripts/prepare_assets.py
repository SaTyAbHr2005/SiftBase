"""Build the site's assets into web/public/assets.

python scripts/prepare_assets.py --photos DIR

DIR holds the three stream photographs (falls.jpg, pool.jpg, bird.jpg, 1376x768, generated with Google
Stitch). For each one this writes the photo, a depth map (Depth Anything V2 Small, Apache-2.0, run
locally) and a water mask. It also downloads one Poly Haven texture (CC0) and generates the caustic tile.
"""
import argparse
import tempfile
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "web" / "public" / "assets"
RIVERBED = ("https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/ganges_river_pebbles/"
            "ganges_river_pebbles_diff_1k.jpg")

# Hand-drawn water in 1376x768 photo pixels. still: pool surfaces that ripple. fall: water that pours.
# keep: areas removed from both (the bird and its frozen splash). gold: ellipses (cx, cy, rx, ry).
SCENES = {
    "falls": {
        "still": [[(450, 365), (900, 362), (960, 385), (700, 395), (470, 400)],
                  [(640, 410), (960, 410), (975, 440), (650, 440)],
                  [(480, 460), (620, 450), (860, 470), (930, 520), (900, 580), (780, 595), (560, 590), (490, 540)],
                  [(960, 500), (1210, 490), (1300, 600), (1376, 640), (1376, 768), (1060, 768), (950, 620)]],
        "fall": [[(540, 190), (585, 188), (600, 355), (530, 355)],
                 [(470, 395), (720, 395), (700, 448), (480, 448)], [(805, 383), (900, 383), (895, 412), (810, 412)],
                 [(705, 595), (800, 590), (830, 700), (850, 768), (720, 768)],
                 [(860, 450), (900, 450), (990, 580), (960, 600)], [(1090, 555), (1130, 555), (1240, 650), (1200, 655)]],
    },
    "pool": {
        "still": [[(0, 190), (760, 190), (700, 330), (0, 350)],
                  [(300, 450), (1376, 430), (1376, 768), (0, 768), (0, 560)]],
        "fall": [[(440, 330), (1376, 110), (1376, 300), (900, 430), (480, 450)]],
        "gold_from_colour": True,
    },
    "bird": {
        "still": [[(0, 560), (1376, 540), (1376, 768), (0, 768)]],
        "fall": [[(635, 150), (715, 150), (722, 360), (628, 360)], [(700, 440), (900, 440), (900, 520), (700, 520)]],
        "keep": [[(790, 265), (950, 170), (1250, 180), (1140, 430), (1130, 610), (1010, 610), (960, 480), (880, 330)],
                 [(940, 500), (1160, 500), (1200, 720), (930, 720)]],
        "gold": [(808, 282, 20, 13)],
    },
}


def fill(polys, shape):
    m = np.zeros(shape, np.uint8)
    for poly in polys:
        cv2.fillPoly(m, [np.array(poly, np.int32)], 255)
    return m.astype(np.float32) / 255


def water_mask(img, spec):
    """RGB mask: R still water, G falling water (follows the bright foam), B gold."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, s, v = hsv[..., 0], hsv[..., 1] / 255, hsv[..., 2] / 255
    keep = 1 - fill(spec.get("keep", []), v.shape)
    still = fill(spec["still"], v.shape) * keep
    fall = fill(spec["fall"], v.shape) * keep * np.clip((v - 0.35) / 0.3, 0.25, 1)
    gold = np.zeros_like(v)
    if spec.get("gold_from_colour"):
        # Measured on the pool photo: nuggets h 20-23, s 0.35-0.65, v median 0.8; silt v <= 0.62, s <= 0.43.
        gold = ((h > 17) & (h < 27)).astype(np.float32) * np.clip((s - 0.3) / 0.1, 0, 1) * np.clip((v - 0.6) / 0.12, 0, 1)
        gold = cv2.morphologyEx(gold, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    for cx, cy, rx, ry in spec.get("gold", []):
        cv2.ellipse(gold, (cx, cy), (rx, ry), 0, 0, 360, 1.0, -1)
    soft = cv2.GaussianBlur((np.dstack([still, fall]) * 255).astype(np.uint8), (0, 0), 3)
    sharp = cv2.GaussianBlur((gold * 255).astype(np.uint8), (0, 0), 1)
    return np.dstack([soft[..., 0], soft[..., 1], sharp])  # RGB order


def depth_maps(paths):
    from transformers import pipeline  # heavy; only needed for the stream photos
    pipe = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf")
    for p in paths:
        img = Image.open(p).convert("RGB")
        d = np.asarray(pipe(img)["predicted_depth"].squeeze(), dtype=np.float32)  # larger = nearer
        d = (d - d.min()) / (d.max() - d.min() + 1e-6)
        yield Image.fromarray((d * 255).astype(np.uint8)).resize(img.size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(2))


def caustic(size=256):
    # Sines on whole periods of the tile, so the pattern repeats without a seam.
    y, x = np.mgrid[0:size, 0:size] / size * 2 * np.pi
    v = np.zeros((size, size))
    for a, b, p in [(3, 1, 0.0), (1, 4, 1.3), (5, -2, 2.1), (-2, 3, 0.7), (4, 5, 2.9)]:
        v += np.sin(a * x + b * y + p + 1.5 * np.sin(b * x - a * y))
    v = 1 - np.abs(v) / np.abs(v).max()
    return Image.fromarray((np.clip(v, 0, 1) ** 6 * 255).astype(np.uint8), "L")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", type=Path, required=True, help="folder with falls.jpg, pool.jpg, bird.jpg")
    args = ap.parse_args()
    stream = OUT / "stream"
    stream.mkdir(parents=True, exist_ok=True)
    for old in ["riverbed-normal.webp", "riverbed-rough.webp", "pan-normal.webp", "pan-rough.webp", "river.hdr"]:
        (OUT / old).unlink(missing_ok=True)

    photos = [args.photos / f"{name}.jpg" for name in SCENES]
    for (name, spec), src, depth in zip(SCENES.items(), photos, depth_maps(photos)):
        Image.open(src).convert("RGB").save(stream / f"{name}.webp", "WEBP", quality=82, method=6)
        depth.save(stream / f"{name}-depth.webp", "WEBP", lossless=True, method=6)
        Image.fromarray(water_mask(cv2.imread(str(src)), spec)).save(stream / f"{name}-water.webp", "WEBP", lossless=True, method=6)

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "riverbed.jpg"
        req = urllib.request.Request(RIVERBED, headers={"User-Agent": "siftbase-assets"})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw.write_bytes(r.read())
        Image.open(raw).convert("RGB").resize((512, 512), Image.LANCZOS).save(OUT / "riverbed-color.webp", "WEBP", quality=72, method=6)
    caustic().save(OUT / "caustic.webp", "WEBP", quality=70, method=6)

    kb = lambda p: f"{p.stat().st_size // 1024} KB"
    lines = [
        "# Asset sources", "",
        "Regenerate every file with `python scripts/prepare_assets.py --photos DIR` (see the script).", "",
        "| File | Source | Licence | Made | Size |", "|---|---|---|---|---|",
    ]
    for name in SCENES:
        lines += [
            f"| stream/{name}.webp | Google Stitch, generated 2026-11-06 for this site | Stitch output | 1376x768 WebP q82 | {kb(stream / f'{name}.webp')} |",
            f"| stream/{name}-depth.webp | Depth Anything V2 Small on the photo | Apache-2.0 model | 8-bit depth, blurred 2px | {kb(stream / f'{name}-depth.webp')} |",
            f"| stream/{name}-water.webp | Hand-drawn polygons in the script | ours | R still, G falling, B gold | {kb(stream / f'{name}-water.webp')} |",
        ]
    lines += [
        f"| riverbed-color.webp | https://polyhaven.com/a/ganges_river_pebbles (Amal Kumar) | CC0 | 1K JPG to 512px WebP q72 | {kb(OUT / 'riverbed-color.webp')} |",
        f"| caustic.webp | generated by the script | ours | 256px tile | {kb(OUT / 'caustic.webp')} |",
    ]
    (OUT / "SOURCES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = sum(f.stat().st_size for f in [*OUT.iterdir(), *stream.iterdir()] if f.is_file() and f.suffix != ".md")
    print("\n".join(lines[6:]), f"\ntotal {total // 1024} KB")


if __name__ == "__main__":
    main()
