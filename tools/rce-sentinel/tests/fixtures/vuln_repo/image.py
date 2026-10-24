from PIL import Image


def thumbnail(path):
    img = Image.open(path)
    img.thumbnail((128, 128))
    return img
