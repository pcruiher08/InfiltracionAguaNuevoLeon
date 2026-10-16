"""Flatten every PNG in informe/figuras onto a white background (RGB, no alpha channel), so PDF viewers that
mishandle transparency masks still draw the maps, charts and logo.

    .venv/bin/python informe/aplanar.py
"""
from pathlib import Path

from PIL import Image

for p in sorted((Path(__file__).resolve().parent / "figuras").glob("*.png")):
    im = Image.open(p)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white"); bg.paste(im, mask=im.split()[-1])
        bg.save(p, optimize=True)
        print("flattened", p.name)
