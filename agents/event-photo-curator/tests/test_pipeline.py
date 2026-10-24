import csv
import hashlib
from io import BytesIO
from pathlib import Path
import sys
from types import SimpleNamespace

import imagehash
from PIL import Image, ImageFilter
import pytest
from typer.testing import CliRunner

from curator.cli import app
from curator.dedupe import group_duplicates
from curator.filters import exposure_flag, sharpness
from curator.loader import Photo, load_image, read_photo
from curator.providers import MockProvider
from curator.report import write_csv, write_html


def test_sharpness_drops_after_blur(sample):
    image = load_image(sample / '01-sharp.png')
    assert sharpness(image) > 100
    assert sharpness(image.filter(ImageFilter.GaussianBlur(8))) < 10
    assert sharpness(Image.new('RGB', (100, 100), 'gray')) == 0


def test_exposure_threshold():
    assert exposure_flag(Image.new('RGB', (10, 10), 'white'), 20) == 'clipped highlights 100.0%'
    assert exposure_flag(Image.new('RGB', (10, 10), 'black'), 20) == 'crushed shadows 100.0%'
    assert exposure_flag(Image.new('RGB', (10, 10), 'gray'), 20) == ''
    assert exposure_flag(Image.new('RGB', (10, 10), 'white'), 100) == ''


def test_dedupe_keeps_sharpest_not_first(sample):
    photos = []
    for name in ['02-burst.png', '01-sharp.png', '04-scene.png']:
        photo, image = read_photo(sample / name)
        photo.sharpness = sharpness(image)
        photo.phash = imagehash.phash(image)
        photos.append(photo)
    assert group_duplicates(photos, 6) == 1
    assert photos[0].duplicate_group == photos[1].duplicate_group
    assert not photos[0].reasons
    assert not photos[1].reasons and not photos[2].duplicate_group


def test_transitive_dedupe_and_eligible_keeper():
    # A-B and B-C match; A-C do not. Group the connected burst once.
    a = Photo(Path('a.jpg'), sharpness=300, phash=imagehash.hex_to_hash('0000000000000000'), reasons=['clipped'])
    b = Photo(Path('b.jpg'), sharpness=200, phash=imagehash.hex_to_hash('0000000000000001'))
    c = Photo(Path('c.jpg'), sharpness=100, phash=imagehash.hex_to_hash('0000000000000003'))
    assert group_duplicates([a, b, c], 1) == 2
    assert len({p.duplicate_group for p in (a, b, c)}) == 1
    assert not b.reasons
    assert not c.reasons


def test_mock_is_monotonic_and_honest():
    photos = [Photo(Path('a.png'), digest='a', sharpness=0), Photo(Path('b.png'), digest='b', sharpness=1000)]
    values, tokens = MockProvider().score(photos, 'casual')
    assert values[0]['score'] == 1 < values[1]['score'] <= 10
    assert all('Mock' in v['caption'] and 'no visual AI' in v['reason'] for v in values)
    assert tokens == 0


def test_preview_resizes_orients_and_strips_metadata(tmp_path):
    path = tmp_path / 'large.jpg'
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = 'Private metadata'
    Image.new('RGB', (2000, 1000), 'gray').save(path, exif=exif)
    photo, image = read_photo(path)
    assert image.size == (512, 1024)
    with Image.open(BytesIO(photo.preview)) as preview:
        assert max(preview.size) == 1024
        assert not preview.getexif()


def test_transparent_png_composites_white(tmp_path):
    path = tmp_path / 'transparent.png'
    Image.new('RGBA', (20, 20), (255, 0, 0, 0)).save(path)
    assert load_image(path).getpixel((0, 0)) == (255, 255, 255)


def test_heic_roundtrip(tmp_path):
    path = tmp_path / 'sample.HEIC'
    Image.new('RGB', (64, 48), (90, 120, 150)).save(path, format='HEIF')
    photo, image = read_photo(path)
    assert image.size == (64, 48) and photo.preview and not photo.reasons


def test_raf_embedded_jpeg_only(tmp_path, monkeypatch):
    buffer = BytesIO()
    Image.new('RGB', (20, 30), 'gray').save(buffer, format='JPEG')
    class Raw:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_thumb(self):
            return SimpleNamespace(format='jpeg', data=buffer.getvalue())
    fake = SimpleNamespace(imread=lambda path: Raw(), ThumbFormat=SimpleNamespace(JPEG='jpeg'))
    monkeypatch.setitem(sys.modules, 'rawpy', fake)
    assert load_image(tmp_path / 'sample.RAF').size == (20, 30)
    monkeypatch.setitem(sys.modules, 'rawpy', None)
    with pytest.raises(ValueError, match='optional dependency'):
        load_image(tmp_path / 'sample.RAF')


def test_csv_and_html_escape_untrusted_text(tmp_path):
    photo = Photo(Path('=SUM(1,2)<x>.png'), sharpness=12, reasons=['<script>alert(1)</script>'])
    write_csv([photo], tmp_path)
    write_html([photo], tmp_path, 'mock', 'sharpness-v1')
    row = list(csv.DictReader((tmp_path / 'report.csv').open()))[0]
    assert row['filename'].startswith("'=")
    html = (tmp_path / 'report.html').read_text()
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert 'Preview unavailable' in html and 'MOCK RUN' in html


def invoke(sample, out, *args):
    return CliRunner().invoke(app, ['run', str(sample), '--out', str(out), '--provider', 'mock', *args])


def test_end_to_end_preserves_originals_and_explains_every_reject(sample, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sample.iterdir()}
    out = tmp_path / 'picks'
    result = invoke(sample, out, '--top', '2')
    assert result.exit_code == 0, result.output
    rows = list(csv.DictReader((out / 'report.csv').open()))
    assert len(rows) == 6
    assert {r['filename'] for r in rows if r['picked'] == 'y'} == {'01-sharp.png', '05-scene.png'}
    assert all(r['reason'] for r in rows if r['picked'] == 'n')
    assert all(before[p.name] == hashlib.sha256(p.read_bytes()).hexdigest() for p in sample.iterdir())
    for p in out.glob('*.png'):
        assert before[p.name] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert (out / 'report.html').read_text().count('<article ') == 6
    again = invoke(sample, out)
    assert again.exit_code != 0 and 'never overwritten' in again.output


@pytest.mark.parametrize('relative', ['photos', 'photos/nested', '.'])
def test_overlapping_output_rejected(sample, tmp_path, relative, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = invoke(sample, tmp_path / relative)
    assert result.exit_code != 0 and 'separate from the input tree' in result.output


def test_corrupt_and_missing_rawpy_are_reported(sample, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, 'rawpy', None)
    (sample / 'broken.png').write_bytes(b'not a photo')
    (sample / 'camera.RAF').write_bytes(b'no raw preview')
    result = invoke(sample, tmp_path / 'out')
    assert result.exit_code == 0, result.output
    rows = list(csv.DictReader((tmp_path / 'out/report.csv').open()))
    failed = [r for r in rows if 'Unreadable:' in r['reason']]
    assert len(failed) == 2 and all(r['picked'] == 'n' for r in failed)


def test_gemini_without_key_warns_and_falls_back(sample, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    result = CliRunner().invoke(app, ['run', str(sample), '--out', str(tmp_path / 'out'), '--provider', 'gemini', '--model', 'gemini-2.5-flash'])
    assert result.exit_code == 0, result.output
    assert 'WARNING' in result.output and 'using mock' in result.output
    assert 'MOCK RUN' in (tmp_path / 'out/report.html').read_text()


def test_blur_flags_never_prevent_ai_review(sample, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = invoke(sample, tmp_path / 'out', '--blur-threshold', '1000000')
    assert result.exit_code == 0, result.output
    rows=list(csv.DictReader((tmp_path / 'out/report.csv').open()))
    assert all(row['ai score'] for row in rows)
    assert all(row['picked']=='y' for row in rows)


def test_empty_input_is_actionable(tmp_path):
    source = tmp_path / 'empty'
    source.mkdir()
    result = invoke(source, tmp_path / 'out')
    assert result.exit_code != 0 and 'No supported photos' in result.output
