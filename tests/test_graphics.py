"""Tests for src/graphics.py."""
from __future__ import annotations

import os

from PIL import Image

from src import graphics


def test_create_stat_card(tmp_path):
    out_path = str(tmp_path / "card.png")
    res = graphics.create_stat_card("Rs 2 Lakh Crore", out_path)
    assert res == out_path
    assert os.path.isfile(out_path)
    assert os.path.getsize(out_path) > 500

    # Verify PNG RGBA image structure
    with Image.open(out_path) as img:
        assert img.mode == "RGBA"
        assert img.size == (800, 240)
        assert img.getpixel((0, 0))[3] == 0, "corners stay transparent (rounded card)"
        assert img.getpixel((400, 120))[3] > 0, "the card body is drawn"


def test_create_stat_card_wraps_long_text(tmp_path):
    """Long key points must wrap inside the card, not run off the edge."""
    out_path = str(tmp_path / "long.png")
    graphics.create_stat_card("A very long key point that cannot fit on one single line",
                              out_path, width=600, height=400)
    with Image.open(out_path) as img:
        assert img.size == (600, 400)
        # text pixels exist well above and below the vertical centre → more than one line
        assert img.getpixel((300, 150))[3] > 0 and img.getpixel((300, 250))[3] > 0


def test_create_stat_card_creates_missing_parent_dir(tmp_path):
    out_path = str(tmp_path / "nested" / "deeper" / "card.png")
    assert graphics.create_stat_card("Ok", out_path) == out_path
    assert os.path.isfile(out_path)
