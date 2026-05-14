"""Generate PWA icons for Netlifegy Mail."""
import os
from PIL import Image, ImageDraw, ImageFont

SIZES = [72, 96, 128, 144, 152, 192, 384, 512]
OUT_DIR = os.path.join(os.path.dirname(__file__), "static", "icons")
os.makedirs(OUT_DIR, exist_ok=True)

BG        = (13,  17,  23)    # #0d1117
ACCENT    = (99, 102, 241)    # #6366f1
ACCENT_LT = (139, 141, 255)   # lighter purple


def draw_icon(size):
    img  = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(img)

    # Rounded-rect mask (simulate rounded corners)
    radius = size // 5
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=ACCENT)

    # Inner dark card
    pad = size // 8
    draw.rounded_rectangle([pad, pad, size - pad - 1, size - pad - 1],
                            radius=radius // 2, fill=BG)

    # Mail envelope icon
    cx, cy = size // 2, size // 2
    w, h   = int(size * 0.45), int(size * 0.30)
    x0, y0 = cx - w // 2, cy - h // 2
    x1, y1 = cx + w // 2, cy + h // 2
    lw = max(2, size // 40)

    # Envelope body
    draw.rectangle([x0, y0, x1, y1], outline=ACCENT_LT, width=lw)

    # Envelope V-fold
    draw.line([x0, y0, cx, cy - lw], fill=ACCENT_LT, width=lw)
    draw.line([x1, y0, cx, cy - lw], fill=ACCENT_LT, width=lw)

    return img


for sz in SIZES:
    icon = draw_icon(sz)
    path = os.path.join(OUT_DIR, f"icon-{sz}.png")
    icon.save(path, "PNG")
    print(f"  ✓  {path}")

print("Done — all icons generated.")
