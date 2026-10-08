"""Generate harmless dummy PNGs for the example_images deck (needs Pillow: use the swipe venv)."""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "images")
os.makedirs(OUT, exist_ok=True)
COLORS = [(52, 101, 164), (78, 154, 6), (204, 0, 0), (245, 121, 0), (117, 80, 123), (193, 125, 17)]
for i, c in enumerate(COLORS, 1):
    w, h = (2400, 1600) if i % 2 else (1200, 1800)
    im = Image.new("RGB", (w, h), c)
    d = ImageDraw.Draw(im)
    for k in range(0, max(w, h), 120):
        d.line([(k, 0), (0, k)], fill=tuple(min(255, x + 40) for x in c), width=8)
    d.ellipse([w // 4, h // 4, 3 * w // 4, 3 * h // 4], outline=(255, 255, 255), width=12)
    try:
        d.text((40, 40), f"DUMMY {i}  {w}x{h}", fill=(255, 255, 255), font_size=96)
    except TypeError:
        d.text((40, 40), f"DUMMY {i}  {w}x{h}", fill=(255, 255, 255))
    im.save(os.path.join(OUT, f"dummy_{i:02d}.png"))
print("wrote", len(COLORS), "dummies to", OUT)
