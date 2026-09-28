#!/usr/bin/env python3
"""Render brand raster assets from the icon geometry (no SVG renderer needed).
Draws at 512px, downscales with LANCZOS. Run from repo root."""
import math
from PIL import Image, ImageDraw

S = 512          # canvas
C = S // 2       # center
NAVY = (23, 32, 51)
RING_OUTER = (71, 99, 158)
RING_INNER = (46, 74, 130)
SWEEP = (22, 119, 255)
BLIP = (47, 201, 99)
CENTER = (157, 185, 242)

def draw_mark(size):
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    u = S / 64  # 64-grid unit
    d.rounded_rectangle([2*u, 2*u, 62*u, 62*u], radius=14*u, fill=NAVY + (255,))
    d.ellipse([C-20*u, C-20*u, C+20*u, C+20*u], outline=RING_OUTER, width=int(2.5*u))
    d.ellipse([C-12*u, C-12*u, C+12*u, C+12*u], outline=RING_INNER, width=int(2*u))
    w = int(2*u)
    for x1, y1, x2, y2 in [(32,10,32,18),(32,46,32,54),(10,32,18,32),(46,32,54,32)]:
        d.line([x1*u, y1*u, x2*u, y2*u], fill=RING_INNER, width=w)
    # sweep wedge: center + arc from -90deg to -30deg (SVG y-down coords)
    pts = [(C, C)]
    for deg in range(-90, -29, 2):
        r = math.radians(deg)
        pts.append((C + 20*u*math.cos(r), C + 20*u*math.sin(r)))
    d.polygon(pts, fill=SWEEP + (255,))
    # blip glow + core at (39,20)
    bx, by = 39*u, 20*u
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [bx-6.5*u, by-6.5*u, bx+6.5*u, by+6.5*u], fill=BLIP + (72,))
    base = Image.alpha_composite(base, glow)
    d = ImageDraw.Draw(base)
    d.ellipse([bx-3.2*u, by-3.2*u, bx+3.2*u, by+3.2*u], fill=BLIP + (255,))
    d.ellipse([C-2.6*u, C-2.6*u, C+2.6*u, C+2.6*u], fill=CENTER + (255,))
    return base.resize((size, size), Image.LANCZOS)

if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    big = draw_mark(S)
    draw_mark(180).save(os.path.join(out, "apple-touch-icon.png"))
    sizes = [48, 32, 16]
    imgs = [draw_mark(s) for s in sizes]
    imgs[0].save(os.path.join(out, "favicon.ico"), sizes=[(s, s) for s in sizes])
    print("wrote apple-touch-icon.png + favicon.ico (16/32/48)")
