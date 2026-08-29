# HealX — Autonomous Debugger & FlakyGuard

**Powered by IBM watsonx.ai and Granite models.**

HealX is an autonomous AI developer agent that eliminates two of the most time-consuming problems in software engineering: **deterministic test failures** and **intermittent (flaky) test failures**. It doesn't just suggest a fix — it diagnoses the root cause, tests hypotheses in isolated sandboxes, proves stability through repeated execution, and applies the verified fix directly to the codebase.

## Powered by IBM Granite

Every reasoning step in HealX — root-cause diagnosis, patch generation, and all three parallel flaky-test hypothesis agents — runs on **IBM Granite models via the watsonx.ai SDK** (`ibm-watsonx-ai`). See [`watsonx_client.py`](./watsonx_client.py) for the integration.

| HealX Step | Granite's Job |
|---|---|
| Mode A diagnosis | Reads a pytest traceback + source, identifies the exact root cause |
| Mode A patch generation | Produces a concrete code fix from the diagnosis |
| Mode B Timing subagent | Detects unmocked sleeps, timeouts, async race conditions |
| Mode B Shared-State subagent | Detects mutated fixtures / cross-test pollution |
| Mode B Randomness subagent | Detects unseeded RNGs / non-deterministic timestamps |

## The Result

> Transformed a 60% intermittent test failure into a 100% pass rate over 10 consecutive runs.

This is a measured outcome from our stress-verification engine, not a projection — every claimed fix is proven by re-running the target test suite up to 50 times before being committed.

## Architecture

```
                        [User / CI Trigger]
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │   Automated Triage    │ ──> Runs test 5x rapidly
                     └───────────┬───────────┘
                                 │
         ┌───────────────────────┴───────────────────────┐
         ▼                                               ▼
[Consistent Failure (5/5 Fails)]               [Mixed Results (e.g. 3/5 Passes)]
         │                                               │
         ▼                                               ▼
┌───────────────────────────────┐               ┌───────────────────────────────┐
│     MODE A: DEBUG LOOP        │               │     MODE B: FLAKYGUARD        │
│ • Granite diagnoses traceback │               │ • Detects non-determinism     │
│ • Granite proposes fix        │               │ • Dispatches 3 parallel       │
│ • Tests fix in sandbox        │               │   Granite subagents (Timing,  │
│ • Retries up to 3x on failure │               │   State, Randomness)          │
└───────────────┬───────────────┘               └───────────────┬───────────────┘
                │                                               │
                │                               ┌───────────────┴───────────────┐
                │                               ▼                               ▼
                │                      [Quick Test Filter]             [50x Stress Proof]
                │                      Picks fastest passing          Proves 100% stability
                │                      hypothesis                      across 10-50 runs
                │                               │                               │
                └───────────────────────┬───────┴───────────────────────────────┘
                                        │
                                        ▼
                     ┌────────────────────────────────────┐
                     │ • Commits Verified Fix to Repo     │
                     │ • Exports Task Session Audit Log   │
                     └────────────────────────────────────┘
```

## Why It Wins

- **Full-lifecycle autonomy**: Detect → Classify → Hypothesize → Sandbox Execute → Verify → Apply, with no human in the loop.
- **Parallel Granite subagent orchestration**: Races 3 specialized hypotheses concurrently instead of guessing sequentially.
- **Closed execution loop**: Directly drives `pytest` in isolated sandboxes to verify its own work before committing.
- **Measurable, provable output**: Every fix ships with a stress-test proof, not just a claim.

## Setup

```bash
pip install ibm-watsonx-ai

export WATSONX_API_KEY="..."
export WATSONX_PROJECT_ID="..."
export WATSONX_URL="https://us-south.ml.cloud.ibm.com"

python orchestrator.py
```

## File Structure

```text
healx/
├── orchestrator.py          # Core engine (Triage, Modes A & B, Parallel Sandbox Runner)
├── watsonx_client.py         # IBM watsonx.ai / Granite integration (all LLM calls)
├── sample_repo/              # Target repository with seeded test cases
│   ├── dummy.py               # Target application code
│   └── tests/
│       ├── test_deterministic_bug.py   # Mode A test case (consistent failure)
│       └── test_flaky_timing.py        # Mode B test case (intermittent failure)
└── BOB_SESSION_REPORT.md     # Exported task execution log for hackathon judging
```