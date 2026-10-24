"""Content-addressed cache and bounded batches, after deterministic filtering."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

from rich.progress import track

from .loader import Photo
from .providers import validate_result


def cache_key(photo: Photo, provider, caption_style: str) -> str:
    context = ['curator-v2-ai-review-all', photo.digest, provider.name, provider.model, caption_style]
    return hashlib.sha256(json.dumps(context, ensure_ascii=True).encode()).hexdigest()


def rank(photos: list[Photo], provider, caption_style: str, cache_dir: Path, batch_size: int, console) -> tuple[int, int]:
    survivors = sorted((p for p in photos if p.preview and not p.reasons),
                       key=lambda p: (bool(p.flags), -p.sharpness, p.path.name))
    if not survivors:
        return 0, 0
    cache_dir.mkdir(parents=True, exist_ok=True)
    pending = []
    aliases = {}
    tokens = hits = 0
    for photo in survivors:
        if photo.digest in aliases:
            aliases[photo.digest].append(photo)
            continue
        aliases[photo.digest] = [photo]
        path = cache_dir / (cache_key(photo, provider, caption_style) + '.json')
        try:
            photo.assessment = validate_result(json.loads(path.read_text(encoding='utf-8')), photo.digest)
            hits += 1
        except (OSError, ValueError, TypeError, UnicodeError):
            pending.append(photo)
    batches = [pending[i:i + batch_size] for i in range(0, len(pending), batch_size)]
    for batch in track(batches, description=f'Ranking ({provider.name})', console=console, disable=not batches):
        results, used = provider.score(batch, caption_style)
        tokens += used
        if len(results) != len(batch) or {item['id'] for item in results} != {p.digest for p in batch}:
            raise RuntimeError('Provider returned mismatched results')
        by_id = {result['id']: validate_result(result, result['id']) for result in results}
        for photo in batch:
            photo.assessment = by_id[photo.digest]
            path = cache_dir / (cache_key(photo, provider, caption_style) + '.json')
            # Atomic replacement means an interrupted run cannot leave partial JSON.
            handle, temporary = tempfile.mkstemp(dir=cache_dir, suffix='.tmp')
            try:
                with os.fdopen(handle, 'w', encoding='utf-8') as stream:
                    json.dump(photo.assessment, stream, ensure_ascii=True)
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
    for members in aliases.values():
        for photo in members[1:]:
            photo.assessment = members[0].assessment
    return tokens, hits
