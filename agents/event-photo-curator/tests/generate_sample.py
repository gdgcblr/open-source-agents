"""Generate public, synthetic fixtures: python tests/generate_sample.py sample-photos."""
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageFilter


def generate(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    images = []
    for _ in range(3):
        tiles = rng.integers(40, 221, size=(24, 32, 3), dtype=np.uint8)
        images.append(Image.fromarray(tiles).resize((640, 480), Image.Resampling.NEAREST))
    images[0].save(folder / '01-sharp.png')
    images[0].filter(ImageFilter.GaussianBlur(0.6)).save(folder / '02-burst.png')
    images[0].filter(ImageFilter.GaussianBlur(8)).save(folder / '03-blurry.jpg')
    images[1].save(folder / '04-scene.png')
    images[2].save(folder / '05-scene.png')
    exposed = images[2].copy()
    exposed.paste('white', (0, 0, 400, 480))
    exposed.save(folder / '06-clipped.png')
    assert len(list(folder.iterdir())) == 6


if __name__ == '__main__':
    generate(Path(sys.argv[1]))
