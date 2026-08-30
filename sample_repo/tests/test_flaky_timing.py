import random
import pytest

@pytest.fixture
def deterministic_random():
    random.seed(0)
    yield random
    random.seed(None)

def test_deterministic(deterministic_random):
    assert deterministic_random.random() > 0.3
