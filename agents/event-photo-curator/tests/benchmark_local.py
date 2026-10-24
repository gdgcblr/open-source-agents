"""Reproducible synthetic ingestion/browsing benchmark, no photos or model calls."""
from io import BytesIO
from pathlib import Path
import tempfile
import time

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image, ImageFilter

from curator.web import create_app


def main():
    rng=np.random.default_rng(123)
    files=[]
    for i in range(100):
        image=Image.fromarray(rng.integers(20,235,(640,960,3),dtype=np.uint8)).filter(ImageFilter.GaussianBlur(.7))
        stream=BytesIO()
        image.save(stream,'JPEG',quality=95)
        files.append(('files',(f'synthetic-{i:03}.jpg',stream.getvalue(),'image/jpeg')))
    original_bytes=sum(len(file[1][1]) for file in files)
    with tempfile.TemporaryDirectory(prefix='curator-benchmark-') as temporary:
        folder=Path(temporary)/'event'
        with TestClient(create_app(folder)) as client:
            client.get('/')
            started=time.perf_counter()
            response=client.post('/api/upload',headers={'X-Curator-Request':'local'},data={'photographer':'Synthetic benchmark','permission':'true'},files=files)
            elapsed=time.perf_counter()-started
            assert response.status_code==200 and len(response.json()['added'])==100,response.text
            started=time.perf_counter()
            page=client.get('/api/photos')
            listing_ms=(time.perf_counter()-started)*1000
            assert len(page.json()['photos'])==48
            thumbs=sum(p.stat().st_size for p in (folder/'thumbs').iterdir())
            assert thumbs<original_bytes/3
            print(f'Imported 100 synthetic 960x640 JPEGs: {elapsed:.2f} s')
            print(f'Gallery first page: 48 metadata records, {len(page.content):,} bytes, {listing_ms:.1f} ms')
            print(f'All thumbnail bytes: {thumbs:,}; original bytes: {original_bytes:,}; ratio: {thumbs/original_bytes:.1%}')
            print('No original bytes are present in gallery JSON. No inference was performed in this benchmark.')


if __name__=='__main__':
    main()
