"""Module for rendering dynamic on-screen graphics, stat cards, and callout badges.

Contract:
    what it does : generates high-resolution, semi-transparent graphic PNGs (stat cards,
                   key-point badges, highlight banners) with PIL for overlay onto video reels.
    input        : text string, optional style parameters, output PNG path.
    output       : path to generated RGBA PNG asset.
    depends on   : PIL (Pillow), src.config.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

from src import config


def _get_font(size: int = 48) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    font_path = config.get("CAPTION_FONT_FILE", os.path.join("assets", "fonts", "Montserrat-Bold.ttf"))
    try:
        if os.path.isfile(font_path):
            return ImageFont.truetype(font_path, size)
    except Exception:  # noqa: BLE001
        pass
    return ImageFont.load_default()


def create_stat_card(text: str, out_path: str, width: int = 800, height: int = 240,
                     bg_color: tuple[int, int, int, int] = (15, 23, 42, 220),
                     border_color: tuple[int, int, int, int] = (245, 158, 11, 255),
                     text_color: tuple[int, int, int, int] = (255, 255, 255, 255)) -> str:
    """Render a sleek, semi-transparent stat card graphic with PIL.

    Returns the path to the generated RGBA PNG file.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw rounded dark background rectangle
    corner_radius = 24
    draw.rounded_rectangle(
        [(0, 0), (width - 1, height - 1)],
        radius=corner_radius,
        fill=bg_color,
        outline=border_color,
        width=4,
    )

    # Wrap & measure text
    font = _get_font(size=52)
    lines = []
    cleaned = text.strip()
    words = cleaned.split()
    cur = ""
    for w in words:
        test = f"{cur} {w}".strip()
        bbox = font.getbbox(test)
        w_len = bbox[2] - bbox[0]
        if w_len > width - 80 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)

    # Vertical centering
    line_height = 64
    total_text_h = len(lines) * line_height
    start_y = (height - total_text_h) // 2

    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        line_w = bbox[2] - bbox[0]
        x = (width - line_w) // 2
        y = start_y + i * line_height
        # Subtle drop shadow
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 180))
        draw.text((x, y), line, font=font, fill=text_color)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path
