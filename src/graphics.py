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


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_font(size: int = 48) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """The caption font at `size`. A relative path is tried from the working directory, then
    from the repo root: resolved against the cwd alone, a run started elsewhere fell back to
    PIL's 10 px bitmap font."""
    font_path = config.get("CAPTION_FONT_FILE", os.path.join("assets", "fonts", "Montserrat-Bold.ttf"))
    for candidate in (font_path, os.path.join(_REPO_ROOT, font_path)):
        try:
            if os.path.isfile(candidate):
                return ImageFont.truetype(candidate, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _wrap(text: str, font, max_width: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        test = f"{cur} {w}".strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] > max_width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


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

    # Wrap, stepping the size down until the lines fit the card: at a fixed 52 px a four-line
    # point ran 256 px tall on a 240 px card.
    cleaned = text.strip()
    for size in (52, 46, 40, 34, 30):
        font = _get_font(size=size)
        lines = _wrap(cleaned, font, width - 80)
        line_height = int(size * 1.23)
        if len(lines) * line_height <= height - 32:
            break

    # Vertical centering
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
