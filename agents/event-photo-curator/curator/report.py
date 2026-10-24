"""CSV audit trail including every scanned photo."""
import csv
from pathlib import Path
from .loader import Photo


FIELDS = ['filename', 'sharpness', 'exposure flag', 'duplicate group', 'ai score', 'reason', 'caption', 'picked']


def write_csv(photos: list[Photo], out: Path):
    with (out / 'report.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(FIELDS)
        for photo in photos:
            reason = '; '.join(photo.reasons) or photo.assessment.get('reason', '')
            if photo.flags:
                reason += ' | Technical hints: ' + '; '.join(photo.flags)
            row = [photo.path.name, f'{photo.sharpness:.2f}', photo.exposure,
                   photo.duplicate_group, photo.assessment.get('score', ''),
                   reason, photo.assessment.get('caption', ''), 'y' if photo.picked else 'n']
            # Spreadsheet programs can interpret untrusted filenames/captions as formulas.
            writer.writerow(["'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')) else value for value in row])


def write_html(photos: list[Photo], out: Path, provider: str, model: str):
    """Self-contained contact sheet: previews work even for HEIC/RAF sources."""
    import base64
    from html import escape
    from urllib.parse import quote

    def card(photo):
        name = escape(photo.path.name)
        reason = '; '.join(photo.reasons) or photo.assessment.get('reason', '')
        if photo.flags:
            reason += ' | Technical hints: ' + '; '.join(photo.flags)
        preview = ('<img loading="lazy" src="data:image/jpeg;base64,'
                   + base64.b64encode(photo.preview).decode() + f'" alt="Preview of {name}">') if photo.preview else '<div class="unreadable">Preview unavailable</div>'
        score = photo.assessment.get('score', 'Not AI ranked')
        criteria = ' · '.join(f'{key.title()}: {photo.assessment[key]:g}/10' for key in ('moment', 'composition', 'expressions') if key in photo.assessment)
        link = f'<a href="{quote(photo.path.name, safe="")}" download>Download original</a>' if photo.picked else ''
        return (f'<article class="card" data-picked="{"y" if photo.picked else "n"}">{preview}<div class="body">'
                f'<h3>{name}</h3><p class="score">Score: {escape(str(score))}</p>'
                f'<p>{escape(criteria)}</p><p class="reason">{escape(reason)}</p>'
                f'<p class="caption">{escape(photo.assessment.get("caption", ""))}</p>'
                f'<p class="technical">Sharpness: {photo.sharpness:.2f} · {escape(photo.exposure or "No exposure flag")}</p>'
                f'{link}</div></article>')

    picked = sorted((p for p in photos if p.picked), key=lambda p: -p.assessment['score'])
    rejected = [p for p in photos if not p.picked]
    warning = '<p class="warning">MOCK RUN — scores use sharpness only. Captions are placeholders; no AI visual judgment.</p>' if provider == 'mock' else ''
    page = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>AfterClick report</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f3ef;color:#202522;font:16px/1.5 system-ui,sans-serif}
main{max-width:1400px;margin:auto;padding:40px 24px}h1{font-size:clamp(28px,5vw,48px);margin:0}h2{margin-top:40px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,280px),1fr));gap:20px}
.card{background:white;border:1px solid #d5d9d2;border-radius:10px;overflow:hidden;min-width:0}
img,.unreadable{width:100%;height:220px;object-fit:contain;background:#e4e7e1}.unreadable{display:grid;place-items:center}
.body{padding:18px}h3{font-size:16px;overflow-wrap:anywhere;margin:0 0 8px}.score{font-weight:700;color:#245138}
p{margin:8px 0;overflow-wrap:anywhere}.technical,.caption{font-size:14px;color:#505950}.warning{background:#fff0bc;padding:16px;border-radius:8px}
a{color:#205936;text-underline-offset:3px}a:focus-visible{outline:3px solid #205936;outline-offset:4px}
</style></head><body><main>'''
    page += (f'<h1>AfterClick</h1><p>{len(photos)} scanned · {len(picked)} picks · {len(rejected)} rejects</p>'
             f'<p>Provider: {escape(provider)} · Model: {escape(model)}</p>{warning}'
             '<p>Scores are editorial suggestions. Review captions and consent before sharing. Original copies retain their metadata.</p>'
             f'<h2>Picks ({len(picked)})</h2><section class="grid" aria-label="Picked photos">'
             + (''.join(card(p) for p in picked) or '<p>No photos passed the selection.</p>')
             + f'</section><h2>Rejects ({len(rejected)})</h2><section class="grid" aria-label="Rejected photos">'
             + (''.join(card(p) for p in rejected) or '<p>No rejected photos.</p>')
             + '</section></main></body></html>')
    (out / 'report.html').write_text(page, encoding='utf-8')
