"""
watsonx_client.py
------------------
Drop-in module that wires IBM watsonx.ai (Granite models) into HealX.

Replace whatever LLM client orchestrator.py currently imports with this
module. It exposes one function per HealX reasoning step:

    1. diagnose_failure()   -> Mode A: root-cause diagnosis from a traceback
    2. generate_patch()     -> Mode A: proposed code fix
    3. run_subagent()       -> Mode B: one of the 3 parallel hypothesis agents
    4. run_subagents_parallel() -> Mode B: races all 3 subagents concurrently

Setup:
    pip install ibm-watsonx-ai

    export WATSONX_API_KEY="..."      # from the hackathon portal
    export WATSONX_PROJECT_ID="..."   # from the hackathon portal
    export WATSONX_URL="https://us-south.ml.cloud.ibm.com"  # region-specific
"""

import os
import concurrent.futures
from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference

# ---------------------------------------------------------------------------
# Config — pull from env vars so credentials never get hardcoded/committed
# ---------------------------------------------------------------------------

CREDENTIALS = Credentials(
    api_key=os.environ["WATSONX_API_KEY"],
    url=os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com"),
)
PROJECT_ID = os.environ["WATSONX_PROJECT_ID"]

# Swap this once you confirm which Granite variants are available on your
# provisioned project (run list(api_client.foundation_models.ChatModels) to check).
# A "*_CODE" variant, if available, is preferable for patch generation.
DIAGNOSIS_MODEL_ID = "ibm/granite-3-3-8b-instruct"
PATCH_MODEL_ID = "ibm/granite-3-3-8b-instruct"
SUBAGENT_MODEL_ID = "ibm/granite-3-3-8b-instruct"


def _get_model(model_id: str) -> ModelInference:
    return ModelInference(
        model_id=model_id,
        credentials=CREDENTIALS,
        project_id=PROJECT_ID,
    )


def _chat(model_id: str, system_prompt: str, user_content: str) -> str:
    model = _get_model(model_id)
    response = model.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    )
    return response["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Mode A: Closed-Loop Debugger
# ---------------------------------------------------------------------------

def diagnose_failure(stack_trace: str, source_context: str) -> str:
    """Given a pytest traceback + surrounding source, return a root-cause
    diagnosis in plain language."""
    system_prompt = (
        "You are a senior debugging agent. Given a Python test failure "
        "traceback and the relevant source code, identify the precise "
        "root cause. Be specific about the line, variable, or condition "
        "responsible. Do not propose a fix yet — diagnosis only."
    )
    user_content = f"TRACEBACK:\n{stack_trace}\n\nSOURCE CONTEXT:\n{source_context}"
    return _chat(DIAGNOSIS_MODEL_ID, system_prompt, user_content)


def generate_patch(diagnosis: str, source_context: str) -> str:
    """Given a diagnosis, propose a concrete code patch."""
    system_prompt = (
        "You are a senior software engineer. Given a root-cause diagnosis "
        "and the relevant source code, output ONLY the corrected code block "
        "needed to fix the issue. No explanation, no markdown fences."
    )
    user_content = f"DIAGNOSIS:\n{diagnosis}\n\nSOURCE CONTEXT:\n{source_context}"
    return _chat(PATCH_MODEL_ID, system_prompt, user_content)


# ---------------------------------------------------------------------------
# Mode B: Parallel FlakyGuard subagents
# ---------------------------------------------------------------------------

SUBAGENT_PROMPTS = {
    "timing": (
        "You are a debugging subagent specialized in TIMING issues. "
        "Inspect the test and source code for unmocked sleep calls, "
        "timeouts, or async race conditions. Propose a fix that removes "
        "the timing dependency (e.g. mock the clock, await the right "
        "event, add a deterministic wait). Output ONLY the corrected code."
    ),
    "state": (
        "You are a debugging subagent specialized in SHARED STATE issues. "
        "Inspect the test and source code for mutated global fixtures or "
        "cross-test state pollution. Propose a fix that isolates state "
        "properly (e.g. fixture scoping, teardown, deep copies). Output "
        "ONLY the corrected code."
    ),
    "randomness": (
        "You are a debugging subagent specialized in NON-DETERMINISM. "
        "Inspect the test and source code for unseeded random generators "
        "or non-deterministic timestamps. Propose a fix that seeds or "
        "mocks the source of randomness. Output ONLY the corrected code."
    ),
}


def run_subagent(kind: str, test_code: str, source_context: str) -> dict:
    """Run a single hypothesis subagent (kind = 'timing' | 'state' | 'randomness')."""
    system_prompt = SUBAGENT_PROMPTS[kind]
    user_content = f"TEST CODE:\n{test_code}\n\nSOURCE CONTEXT:\n{source_context}"
    patch = _chat(SUBAGENT_MODEL_ID, system_prompt, user_content)
    return {"kind": kind, "patch": patch}


def run_subagents_parallel(test_code: str, source_context: str) -> list[dict]:
    """Race all 3 hypothesis subagents concurrently. Returns a list of
    {kind, patch} dicts — feed each into your sandbox test runner and
    keep the first one that passes the quick filter."""
    kinds = ["timing", "state", "randomness"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_subagent, kind, test_code, source_context): kind
            for kind in kinds
        }
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    return results