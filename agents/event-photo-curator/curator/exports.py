"""Full-resolution JPEG derivatives; stored originals remain byte-identical."""
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def export_jpeg(path: Path, photographer: str, watermark: str = '') -> bytes:
    # RAF exports use its embedded JPEG; the original RAF download stays untouched.
    if path.suffix.lower() == '.raf':
        import rawpy
        with rawpy.imread(str(path)) as raw:
            thumb = raw.extract_thumb()
            if thumb.format != rawpy.ThumbFormat.JPEG:
                raise ValueError('RAF has no embedded JPEG')
            source = Image.open(BytesIO(thumb.data))
    else:
        source = Image.open(path)
    with source:
        image = ImageOps.exif_transpose(source).convert('RGB')
        if watermark:
            draw = ImageDraw.Draw(image)
            font = ImageFont.load_default(size=max(14, min(image.size) // 30))
            bounds = draw.textbbox((0, 0), watermark, font=font)
            margin = max(12, min(image.size) // 40)
            x = max(margin, image.width - (bounds[2] - bounds[0]) - margin)
            y = max(margin, image.height - (bounds[3] - bounds[1]) - margin)
            draw.text((x, y), watermark, font=font, fill='white', stroke_width=2, stroke_fill='black', anchor='lt')
        # Derivatives strip inherited GPS/private EXIF; attribution is added explicitly.
        exif = Image.Exif()
        if photographer:
            exif[315] = photographer
            exif[33432] = f'Photo: {photographer}'
        output = BytesIO()
        image.save(output, 'JPEG', quality=95, exif=exif)
        return output.getvalue()
