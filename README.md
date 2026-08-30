# HealX — Autonomous AI Debugger & FlakyGuard

**Powered by IBM Granite via watsonx.ai**

HealX is an autonomous AI developer agent that eliminates two of the most time-consuming problems in software engineering: **deterministic test failures** and **intermittent (flaky) test failures**. It doesn't just suggest a fix — it diagnoses the root cause, tests hypotheses in isolated sandboxes, proves stability through repeated execution, and applies the verified fix directly to your codebase.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/shorouq-iqbal/bob-The-dual-mode-debugger.git
cd bob-The-dual-mode-debugger
pip install -e .
```

### 2. Set credentials

```bash
# Windows PowerShell
$env:WATSONX_API_KEY = "your-api-key"
$env:WATSONX_PROJECT_ID = "your-project-id"

# Linux / macOS
export WATSONX_API_KEY="your-api-key"
export WATSONX_PROJECT_ID="your-project-id"
```

### 3. Run on the bundled demo

```bash
# Mode A — deterministic bug
heal-x --repo sample_repo tests/test_deterministic_bug.py

# Mode B — flaky test
heal-x --repo sample_repo tests/test_flaky_timing.py
```

### 4. Launch the live web dashboard

```bash
python run_demo.py
# Opens http://localhost:8000 automatically
```

---

## How to Use HealX on Any Project

HealX works on **any Python project** that uses pytest. No configuration files or code changes needed inside the target project.

### Basic usage

```bash
# Point --repo at your project root, give it a failing test path
heal-x --repo /path/to/your/project tests/test_something.py
```

### From inside your project directory

```bash
cd /path/to/your/project
heal-x tests/test_something.py        # --repo defaults to current directory
```

### Windows examples

```powershell
heal-x --repo C:\MyProject tests/test_calculator.py
heal-x --repo C:\work\api-service tests/unit/test_auth.py
```

### What your project needs

| Requirement | Details |
|---|---|
| Python source file | Any `.py` file with a bug |
| A failing pytest test | The test that catches the bug |
| Importable source | Test must be able to `import` the module (add a `conftest.py` with `sys.path` if needed) |

### Example: fixing a bug in your own project

**Your project structure:**
```
C:\MyProject\
    calculator.py          ← has a bug
    tests\
        test_calculator.py ← test that fails
```

**`calculator.py`** (buggy):
```python
def multiply(a, b):
    return a * b + 1      # off-by-one bug
```

**`tests/test_calculator.py`**:
```python
from calculator import multiply

def test_multiply():
    assert multiply(3, 4) == 12
```

**Run HealX:**
```powershell
heal-x --repo C:\MyProject tests/test_calculator.py
```

**What happens:**
```
Triage        → 5 runs, all FAIL → Deterministic Bug (Mode A)
Granite       → diagnoses: "multiply returns a*b+1, should be a*b"
Patch         → generates: return a * b
Sandbox test  → patch passes in isolation
Stress verify → 50/50 runs pass
Apply fix     → calculator.py updated in place
Report        → HEALX_REPORT_<timestamp>.md written
```

### Example: fixing a flaky test

**Your flaky test:**
```python
import random

def test_network_retry():
    # Flaky: sometimes fails depending on random backoff
    assert random.random() > 0.2
```

**Run HealX:**
```powershell
heal-x --repo C:\MyProject tests/test_network_retry.py
```

**What happens:**
```
Triage        → mixed results (3 pass, 2 fail) → Flaky Test (Mode B)
Subagents     → 3 IBM Granite agents race in parallel:
                  Timing     → checks for sleep/async issues   ✗
                  State      → checks for shared state leaks   ✗
                  Randomness → detects unseeded RNG            ✓  WINNER
Patch         → seeds random.seed(42) to make test deterministic
Stress verify → 10/10 runs pass
Apply fix     → test file updated in place
```

---

## CLI Reference

```
heal-x [OPTIONS] [TEST_PATH]

Arguments:
  TEST_PATH    Relative path to the pytest test file
               Default: tests/test_deterministic_bug.py

Options:
  --repo, -r   Path to the project root directory
               Default: current working directory
  --no-report  Skip writing the Markdown audit report
  --help       Show this message and exit
```

---

## Web Dashboard

```bash
python run_demo.py
```

| Section | What you see |
|---|---|
| Triage Grid | 5 live badges turning green/red as runs complete |
| Classification | DETERMINISTIC BUG or FLAKY TEST with routing decision |
| Subagent Race Board | 3 Granite agents: PENDING → ANALYZING → PASSED/FAILED |
| Code Diff Card | Syntax-highlighted before/after patch |
| Stress Verification | Live progress bar (e.g. 24/50 runs) |
| Audit Report | Download link to Markdown report |

---

## Powered by IBM Granite

Every reasoning step runs on **IBM Granite models via watsonx.ai**:

| Step | Granite's Job |
|---|---|
| Mode A diagnosis | Reads pytest traceback + source, identifies exact root cause |
| Mode A patch | Produces a concrete code fix from the diagnosis |
| Mode B Timing agent | Detects unmocked sleeps, timeouts, async race conditions |
| Mode B State agent | Detects mutated fixtures / cross-test state pollution |
| Mode B Randomness agent | Detects unseeded RNGs / non-deterministic timestamps |

---

## Architecture

```
                        [User / CI Trigger]
                                 │
                        heal-x --repo . tests/...
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │   Automated Triage    │  5 runs to classify
                     └───────────┬───────────┘
                                 │
         ┌───────────────────────┴───────────────────────┐
         ▼                                               ▼
[Consistent Failure]                          [Mixed Results]
         │                                               │
         ▼                                               ▼
┌─────────────────────┐                    ┌─────────────────────────┐
│  MODE A: DEBUG LOOP │                    │   MODE B: FLAKYGUARD    │
│ • Granite diagnoses │                    │ • 3 Granite subagents   │
│ • Granite patches   │                    │   run in parallel       │
│ • Sandbox test      │                    │ • Timing / State /      │
│ • Retry up to 3x    │                    │   Randomness hypotheses │
└──────────┬──────────┘                    └───────────┬─────────────┘
           │                                           │
           └─────────────────┬─────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  Stress Verify (10–50 runs)  │
              │  Apply fix to source repo    │
              │  Write Markdown audit report │
              └──────────────────────────────┘
```

---

## File Structure

```
healx/
├── healx_cli.py          # Rich/Typer CLI — heal-x command
├── orchestrator.py       # Core engine (Triage, Mode A, Mode B, sandboxing)
├── watsonx_client.py     # IBM Granite integration (all LLM calls)
├── reporter.py           # Markdown audit report generator
├── app.py                # FastAPI + SSE backend for web dashboard
├── static/index.html     # Dark-mode live dashboard (Tailwind CSS)
├── run_demo.py           # One-command demo launcher (opens browser)
├── pyproject.toml        # pip install -e . → heal-x command
├── requirements.txt      # All dependencies
└── sample_repo/
    ├── dummy.py                         # Seeded bug: return a + b + 1
    └── tests/
        ├── test_deterministic_bug.py    # Mode A demo test
        ├── test_flaky_timing.py         # Mode B demo test (unseeded random)
        └── conftest.py                  # sys.path fix for pytest
```

---

## Reset for Demo

After HealX fixes the bugs, restore them before demoing again:

```powershell
# Windows PowerShell
Set-Content sample_repo\dummy.py "def add(a, b):`n    return a + b + 1`n"
Set-Content sample_repo\tests\test_flaky_timing.py "import random`n`n`ndef test_flaky():`n    assert random.random() > 0.3`n"
```

```bash
# Linux / macOS
echo -e "def add(a, b):\n    return a + b + 1\n" > sample_repo/dummy.py
echo -e "import random\n\n\ndef test_flaky():\n    assert random.random() > 0.3\n" > sample_repo/tests/test_flaky_timing.py
```

---

*HealX — IBM Hackathon 2026 · Built with IBM Granite via watsonx.ai*
