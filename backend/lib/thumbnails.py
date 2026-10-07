"""Shape Kannada with HarfBuzz and render real font glyphs with FreeType."""
import os
import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw


def font_path() -> str:
    path = os.environ.get("THUMBNAIL_FONT_PATH", "C:/Windows/Fonts/NirmalaB.ttf")
    if not Path(path).is_file():
        raise ValueError("Configure THUMBNAIL_FONT_PATH with a Kannada-capable font.")
    return path


def validate_headlines(lines, language: str) -> list[str]:
    count = 3 if language == "kn" else 2
    if isinstance(lines, list) and len(lines) > count:
        lines = lines[:count]
    if not isinstance(lines, list) or len(lines) != count or any(not isinstance(s, str) or not s.strip() for s in lines):
        raise ValueError(f"Provide {count} short thumbnail headlines before generating an image.")
    lines = [s.strip() for s in lines]
    if any(len(s) > 90 or "\n" in s for s in lines):
        raise ValueError("Keep each thumbnail headline to one short line (90 characters maximum).")
    if language == "kn" and any(re.search(r"[A-Za-z]", s) or not re.search(r"[\u0c80-\u0cff]", s) for s in lines):
        raise ValueError("Kannadiga headlines must use Kannada script without English words.")
    if language == "kn":
        # Letters, vowel signs or digits of another script (seen: Gujarati letters inside a Kannada word). The lines
        # become the thumbnail text and the post title, so they must be clean Kannada.
        foreign = sorted({c for s in lines for c in s if unicodedata.category(c)[0] in "LMN"
                          and not ("\u0c80" <= c <= "\u0cff" or c.isascii())})
        if foreign:
            raise ValueError("Kannadiga headlines must use Kannada script only; found letters from another script: "
                             + " ".join(f"{c} (U+{ord(c):04X})" for c in foreign))
    return lines


def shaped_line(text: str, size: int) -> Image.Image:
    import freetype
    import uharfbuzz as hb

    path = font_path()
    data = Path(path).read_bytes()
    font = hb.Font(hb.Face(data))
    font.scale = (size * 64, size * 64)
    hb.ot_font_set_funcs(font)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf)
    face = freetype.Face(path)
    face.set_pixel_sizes(0, size)
    glyphs, pen_x, pen_y = [], 0, 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        if info.codepoint == 0:
            raise ValueError("The thumbnail font is missing a required character.")
        face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER)
        bit = face.glyph.bitmap
        x = round((pen_x + pos.x_offset) / 64) + face.glyph.bitmap_left
        y = -round((pen_y + pos.y_offset) / 64) - face.glyph.bitmap_top
        if bit.width and bit.rows:
            raw = bytes(bit.buffer)
            rows = [raw[i * abs(bit.pitch):i * abs(bit.pitch) + bit.width] for i in range(bit.rows)]
            if bit.pitch < 0:
                rows.reverse()
            glyphs.append((x, y, Image.frombytes("L", (bit.width, bit.rows), b"".join(rows))))
        pen_x += pos.x_advance
        pen_y += pos.y_advance
    if not glyphs:
        raise ValueError("The headline has no visible characters.")
    left = min(x for x, y, im in glyphs)
    top = min(y for x, y, im in glyphs)
    right = max(x + im.width for x, y, im in glyphs)
    bottom = max(y + im.height for x, y, im in glyphs)
    canvas = Image.new("L", (right - left + 4, bottom - top + 4))
    for x, y, im in glyphs:
        canvas.paste(im, (x - left + 2, y - top + 2), im)
    return canvas


def add_headlines(image: Image.Image, lines: list[str], language: str) -> Image.Image:
    lines = validate_headlines(lines, language)
    image = image.convert("RGB")
    if image.width * 9 != image.height * 16:
        raise ValueError("The provider returned an image that is not 16:9.")
    width, height = image.size
    band = int(height * (0.36 if language == "kn" else 0.30))
    ImageDraw.Draw(image).rectangle((0, 0, width, band), fill="#090f18")
    # Choose one common scale so the second headline stays typographically largest.
    sizes = [55, 78, 46] if language == "kn" else [56, 88]
    masks = [shaped_line(text, size) for text, size in zip(lines, sizes)]
    factor = min(2, (width - 96) / max(m.width for m in masks), (band - 48 - 14 * (len(lines) - 1)) / sum(m.height for m in masks))
    if min(sizes[:len(lines)]) * factor < 28:
        raise ValueError("Thumbnail headlines are too long for mobile readability; shorten them.")
    y = 24
    for index, mask in enumerate(masks):
        mask = mask.resize((max(1, round(mask.width * factor)), max(1, round(mask.height * factor))), Image.Resampling.LANCZOS)
        image.paste("#ffd34e" if index == 1 else "#ffffff", ((width - mask.width) // 2, y), mask)
        y += mask.height + 14
    return image
