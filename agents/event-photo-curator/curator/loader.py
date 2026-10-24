"""Decode previews without changing source files."""
from dataclasses import dataclass, field
import hashlib
import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 80_000_000
warnings.filterwarnings('error', category=Image.DecompressionBombWarning)
SUPPORTED = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.raf'}


@dataclass
class Photo:
    path: Path
    digest: str = ''
    preview: bytes = b''
    sharpness: float = 0.0
    exposure: str = ''
    phash: object = None
    duplicate_group: str = ''
    flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    assessment: dict = field(default_factory=dict)
    picked: bool = False


def load_image(path: Path, max_edge: int = 1024) -> Image.Image:
    if path.suffix.lower() == '.raf':
        try:
            import rawpy
        except ImportError:
            raise ValueError('RAF requires optional dependency: pip install rawpy') from None
        with rawpy.imread(str(path)) as raw:
            thumb = raw.extract_thumb()
            if thumb.format != rawpy.ThumbFormat.JPEG:
                raise ValueError('RAF has no supported embedded JPEG thumbnail')
            with Image.open(BytesIO(thumb.data)) as source:
                return normalize(source, max_edge)
    with Image.open(path) as source:
        return normalize(source, max_edge)


def normalize(source: Image.Image, max_edge: int = 1024) -> Image.Image:
    image = ImageOps.exif_transpose(source)
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    # Composite transparency onto white rather than scoring hidden RGB values.
    if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
        rgba = image.convert('RGBA')
        background = Image.new('RGBA', rgba.size, 'white')
        image = Image.alpha_composite(background, rgba)
    return image.convert('RGB')


def read_photo(path: Path) -> tuple[Photo, Image.Image | None]:
    photo = Photo(path=path)
    try:
        with path.open('rb') as stream:
            photo.digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        image = load_image(path)
        buffer = BytesIO()
        # A fresh image strips EXIF, GPS and other source metadata from previews.
        clean = Image.new('RGB', image.size)
        clean.paste(image)
        clean.save(buffer, format='JPEG', quality=85)
        photo.preview = buffer.getvalue()
        return photo, image
    except Exception as exc:
        # Bad files must not stop a whole event folder; only expose the error type.
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        photo.reasons.append(f'Unreadable: {detail}')
        return photo, None
