"""Icons drawn with Pillow at runtime (no image files needed)."""
from __future__ import annotations

from PIL import Image, ImageDraw
import customtkinter as ctk

_S = 4  # supersampling factor for smooth edges


def _draw(name: str, size: int, color: str) -> Image.Image:
    px = size * _S
    k = px / 24.0
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(1, int(2 * k))

    def box(x0, y0, x1, y1):
        return [x0 * k, y0 * k, x1 * k, y1 * k]

    def line(pts, width=w):
        d.line([(x * k, y * k) for x, y in pts], fill=color, width=width, joint="curve")

    if name == "dashboard":
        for x0, y0 in ((3, 3), (13, 3), (3, 13), (13, 13)):
            d.rounded_rectangle(box(x0, y0, x0 + 8, y0 + 8), radius=2 * k, fill=color)
    elif name == "cpu":
        d.rounded_rectangle(box(6, 6, 18, 18), radius=2 * k, outline=color, width=w)
        d.rectangle(box(10, 10, 14, 14), fill=color)
        for p in (9, 12, 15):
            line([(p, 2.5), (p, 6)]); line([(p, 18), (p, 21.5)])
            line([(2.5, p), (6, p)]); line([(18, p), (21.5, p)])
    elif name == "memory":
        d.rounded_rectangle(box(2, 6, 22, 17), radius=2 * k, outline=color, width=w)
        for x in (5, 10.5, 16):
            d.rectangle(box(x, 9.5, x + 3, 13.5), fill=color)
        for x in (6, 10, 14, 18):
            line([(x, 17), (x, 20)])
    elif name == "process":
        for y in (6, 12, 18):
            d.ellipse(box(3, y - 1.6, 6.2, y + 1.6), fill=color)
            line([(9, y), (21, y)])
    elif name == "storage":
        d.rounded_rectangle(box(2.5, 6, 21.5, 18), radius=3 * k, outline=color, width=w)
        line([(6, 12), (12, 12)])
        d.ellipse(box(15.5, 10.5, 18.5, 13.5), fill=color)
    elif name == "network":
        for x0, y0 in ((4, 14), (10, 9), (16, 3.5)):
            d.rounded_rectangle(box(x0, y0, x0 + 4, 20.5), radius=1 * k, fill=color)
    elif name == "diagnostics":
        line([(2, 12), (7, 12), (9.5, 5.5), (13.5, 18.5), (16, 12), (22, 12)], width=int(2.2 * k))
    elif name == "history":
        d.ellipse(box(3, 3, 21, 21), outline=color, width=w)
        line([(12, 7), (12, 12), (16, 14.5)])
    elif name == "logo":
        d.rounded_rectangle(box(0.5, 0.5, 23.5, 23.5), radius=6 * k, fill=color)
        pts = [(4, 12.5), (8, 12.5), (10, 7), (14, 18), (16, 12.5), (20, 12.5)]
        d.line([(x * k, y * k) for x, y in pts], fill="#0D1117", width=int(2.4 * k), joint="curve")
    return img.resize((size, size), Image.Resampling.LANCZOS)


def pil_icon(name: str, size: int = 22, color: str = "#8896AB") -> Image.Image:
    return _draw(name, size, color)


def ctk_icon(name: str, size: int = 20, color: str = "#8896AB") -> ctk.CTkImage:
    img = _draw(name, size * 2, color)  # drawn at 2x so it stays crisp on high-DPI screens
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
