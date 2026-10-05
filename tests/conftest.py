import pytest

from PyFlow import Model


@pytest.fixture
def model():
    return Model(seed=1)
