"""Opt-in, event-local YuNet/SFace matching. Selfie queries are never saved."""

import hashlib
from pathlib import Path
import urllib.request

import cv2
import numpy as np
from PIL import Image

MODELS = {
    "face_detection_yunet": (
        "face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface": (
        "face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def download_models(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    for kind, (name, expected) in MODELS.items():
        path = folder / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            continue
        url = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/{kind}/{name}"
        temporary = path.with_suffix(".download")
        try:
            with urllib.request.urlopen(url, timeout=120) as stream, temporary.open(
                "wb"
            ) as out:
                while chunk := stream.read(1024 * 1024):
                    out.write(chunk)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
                raise ValueError("Face model checksum mismatch")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


class FaceMatcher:
    def __init__(self, folder: Path):
        paths = [folder / value[0] for value in MODELS.values()]
        if not all(p.is_file() for p in paths):
            raise ValueError(
                "Face models are missing. Run python -m curator models first."
            )
        self.detector = cv2.FaceDetectorYN.create(
            str(paths[0]), "", (320, 320), 0.8, 0.3, 5000
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(paths[1]), "")

    def detect(self, image: Image.Image, recognize: bool = False) -> list[dict]:
        rgb = image.convert("RGB").copy()
        rgb.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        bgr = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
        height, width = bgr.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(bgr)
        results = []
        for face in faces if faces is not None else []:
            x, y, w, h = map(float, face[:4])
            if min(w, h) < 24:
                continue
            left, top = max(0.0, x / width), max(0.0, y / height)
            right, bottom = min(1.0, (x + w) / width), min(1.0, (y + h) / height)
            if right <= left or bottom <= top:
                continue
            record = {
                "box": [left, top, right - left, bottom - top],
                "detection_score": float(face[-1]),
            }
            if recognize:
                record["embedding"] = self.recognizer.feature(
                    self.recognizer.alignCrop(bgr, face)
                )[0].tolist()
            results.append(record)
        return results

    def encode(self, image: Image.Image) -> list[dict]:
        return self.detect(image, recognize=True)

    @staticmethod
    def similarity(a, b) -> float:
        a, b = np.asarray(a), np.asarray(b)
        denominator = np.linalg.norm(a) * np.linalg.norm(b)
        return float(np.dot(a, b) / denominator) if denominator else 0.0


def match_faces(references, faces, threshold, team=False):
    """One target face per person, with ambiguity surfaced instead of identity claims."""
    candidates = []
    for face_index, face in enumerate(faces):
        scores = [
            FaceMatcher.similarity(ref["embedding"], face["embedding"])
            for ref in references
        ]
        for reference_index, score in enumerate(scores):
            if score >= threshold:
                candidates.append((score, reference_index, face_index))
    candidates.sort(reverse=True)
    selected, used_references, used_faces = [], set(), set()
    for score, reference_index, face_index in candidates:
        if face_index in used_faces or (team and reference_index in used_references):
            continue
        alternatives = [
            s for s, r, f in candidates if r == reference_index and f != face_index
        ]
        ambiguous = bool(alternatives and score - max(alternatives) < 0.05)
        selected.append(
            {
                "box": faces[face_index]["box"],
                "similarity": round(score, 3),
                "reference_index": reference_index,
                "ambiguous": ambiguous,
            }
        )
        used_faces.add(face_index)
        used_references.add(reference_index)
        if not team:
            break
    return selected
