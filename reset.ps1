Set-Content sample_repo\dummy.py "def add(a, b):
    return a + b + 1
"
Set-Content sample_repo\tests\test_flaky_timing.py "import random


def test_flaky():
    assert random.random() > 0.3
"
Write-Host "Bugs restored - ready to demo"
