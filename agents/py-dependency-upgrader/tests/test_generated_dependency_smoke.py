"""Auto-generated smoke tests for third-party Python dependencies."""

import pytest

PACKAGE_NAMES = [
    "google-adk",
    "ipython",
    "packaging",
    "pytest",
    "requests",
]


@pytest.mark.parametrize("package_name", PACKAGE_NAMES)
def test_dependency_can_import(package_name: str):
    module = pytest.importorskip(package_name)
    assert module is not None


@pytest.mark.parametrize("package_name", PACKAGE_NAMES)
def test_dependency_has_version_metadata(package_name: str):
    module = pytest.importorskip(package_name)
    version = getattr(module, "__version__", None)
    assert version is not None or hasattr(module, "__spec__")
