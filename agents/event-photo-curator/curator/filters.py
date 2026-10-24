"""Cheap quality measurements on a maximum 1024px preview."""
import cv2
import numpy as np
from PIL import Image


def sharpness(image: Image.Image) -> float:
    gray = np.asarray(image.convert('L'))
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def exposure_flag(image: Image.Image, clip_percent: float) -> str:
    gray = np.asarray(image.convert('L'))
    shadows = float(np.mean(gray <= 5) * 100)
    highlights = float(np.mean(gray >= 250) * 100)
    flags = []
    if highlights > clip_percent:
        flags.append(f'clipped highlights {highlights:.1f}%')
    if shadows > clip_percent:
        flags.append(f'crushed shadows {shadows:.1f}%')
    return '; '.join(flags)
