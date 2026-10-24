from android_tools import search_android_knowledge


def test_firebase_error():
    result = search_android_knowledge(
        "google-services.json is missing"
    )
    assert result["found"] is True
    assert result["category"] == "Firebase"


def test_gradle_error():
    result = search_android_knowledge(
        "Could not resolve dependencies"
    )
    assert result["found"] is True
    assert result["category"] == "Gradle"


def test_unknown_error():
    result = search_android_knowledge(
        "Unknown database connection failure"
    )
    assert result["found"] is False


if __name__ == "__main__":
    test_firebase_error()
    test_gradle_error()
    test_unknown_error()
    print("All Android knowledge tests passed!")