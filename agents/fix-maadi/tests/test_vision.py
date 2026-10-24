import json
import unittest
from unittest.mock import patch

from vision import infer_image


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps({
            "description": "A deep pothole is visible on the road",
            "category": "Pothole / road damage",
            "confidence": "high",
            "safety_flags": ["traffic risk"],
        })}]}}]}).encode()


class VisionProviderTests(unittest.TestCase):
    def test_gemini_response_is_validated_and_normalized(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"}, clear=False), patch("vision.urllib.request.urlopen", return_value=FakeResponse()):
            result = infer_image("aGVsbG8=", "image/jpeg", "street context")
        self.assertEqual(result["provider"], "gemini")
        self.assertEqual(result["category"], "Pothole / road damage")


if __name__ == "__main__":
    unittest.main()
