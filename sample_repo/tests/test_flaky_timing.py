import random


def test_flaky():
    random.seed(0)
    assert random.random() > 0.3
