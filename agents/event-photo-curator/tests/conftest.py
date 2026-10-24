import pytest

from tests.generate_sample import generate


@pytest.fixture
def sample(tmp_path):
    folder = tmp_path / 'photos'
    generate(folder)
    return folder
