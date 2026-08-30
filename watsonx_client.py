"""
watsonx_client.py
------------------
Drop-in module that wires IBM watsonx.ai (Granite models) into HealX.
"""

import os
import warnings
import concurrent.futures
from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference

# Suppress the noisy "max_tokens was set to 1024" warning from watsonx SDK
warnings.filterwarnings("ignore", category=UserWarning, module="ibm_watsonx_ai")
warnings.filterwarnings("ignore", message=".*max_tokens.*", category=Warning)

# Credentials are resolved lazily on first use so that importing this
# module (e.g. for --help) never crashes when env vars are absent.
_CREDENTIALS = None
_PROJECT_ID = None


def _get_credentials():
    global _CREDENTIALS, _PROJECT_ID
    if _CREDENTIALS is None:
        api_key = os.environ.get("WATSONX_API_KEY")
        project_id = os.environ.get("WATSONX_PROJECT_ID")
        if not api_key:
            raise EnvironmentError(
                "WATSONX_API_KEY environment variable is not set.\n"
                "Export it before running: set WATSONX_API_KEY=<your-key>"
            )
        if not project_id:
            raise EnvironmentError(
                "WATSONX_PROJECT_ID environment variable is not set.\n"
                "Export it before running: set WATSONX_PROJECT_ID=<your-project-id>"
            )
        _CREDENTIALS = Credentials(
            api_key=api_key,
            url=os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com"),
        )
        _PROJECT_ID = project_id
    return _CREDENTIALS, _PROJECT_ID

# Confirmed working on this project's provisioning (2026-08-29).
# granite-3-1-8b-base does NOT support chat (base/completion model only).
# granite-guardian-3-8b is a safety/guardrail model, not for general reasoning.
# granite-4-h-small is the only general-purpose instruct Granite chat model
# available on this project -- use it everywhere.
DIAGNOSIS_MODEL_ID = "ibm/granite-4-h-small"
PATCH_MODEL_ID = "ibm/granite-4-h-small"
SUBAGENT_MODEL_ID = "ibm/granite-4-h-small"


def _get_model(model_id: str) -> ModelInference:
    credentials, project_id = _get_credentials()
    return ModelInference(
        model_id=model_id,
        credentials=credentials,
        project_id=project_id,
    )


def _strip_code_fences(text: str) -> str:
    """Robustly strip markdown code fences regardless of language tag or
    leading/trailing whitespace/newlines."""
    text = text.strip()
    lines = text.split("\n")
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# Max tokens to request — set explicitly to avoid the SDK warning
_MAX_TOKENS = 1024


def _chat(model_id: str, system_prompt: str, user_content: str) -> str:
    model = _get_model(model_id)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        response = model.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            params={"max_new_tokens": _MAX_TOKENS},
        )
    return response["choices"][0]["message"]["content"]


def diagnose_failure(stack_trace: str, source_context: str) -> str:
    system_prompt = (
        "You are a senior debugging agent. Given a Python test failure "
        "traceback and the relevant source code, identify the precise "
        "root cause. Be specific about the line, variable, or condition "
        "responsible. Do not propose a fix yet — diagnosis only."
    )
    user_content = f"TRACEBACK:\n{stack_trace}\n\nSOURCE CONTEXT:\n{source_context}"
    return _chat(DIAGNOSIS_MODEL_ID, system_prompt, user_content)


def generate_patch(diagnosis: str, source_context: str) -> str:
    system_prompt = (
        "You are a senior software engineer. Given a root-cause diagnosis "
        "and the relevant source code, output ONLY the corrected code block "
        "needed to fix the issue. No explanation, no markdown fences."
    )
    user_content = f"DIAGNOSIS:\n{diagnosis}\n\nSOURCE CONTEXT:\n{source_context}"
    raw = _chat(PATCH_MODEL_ID, system_prompt, user_content)
    return _strip_code_fences(raw)


_CODE_ONLY = (
    " Output ONLY valid Python source code for the complete fixed test file."
    " Do NOT include explanations, prose, or markdown fences."
    " The output must be directly runnable by pytest as-is."
)

SUBAGENT_PROMPTS = {
    "timing": (
        "You are a debugging subagent specialized in TIMING issues. "
        "Inspect the test and source code for unmocked sleep calls, "
        "timeouts, or async race conditions. Propose a fix that removes "
        "the timing dependency (e.g. mock the clock, add a deterministic wait)."
        + _CODE_ONLY
    ),
    "state": (
        "You are a debugging subagent specialized in SHARED STATE issues. "
        "Inspect the test and source code for mutated global fixtures or "
        "cross-test state pollution. Propose a fix that isolates state "
        "properly (e.g. fixture scoping, teardown, deep copies)."
        + _CODE_ONLY
    ),
    "randomness": (
        "You are a debugging subagent specialized in NON-DETERMINISM. "
        "Inspect the test and source code for unseeded random generators "
        "or non-deterministic behaviour. Seed or mock the randomness source "
        "so the test always passes deterministically."
        + _CODE_ONLY
    ),
}


def run_subagent(kind: str, test_code: str, source_context: str) -> dict:
    system_prompt = SUBAGENT_PROMPTS[kind]
    user_content = (
        f"TEST CODE:\n{test_code}\n\n"
        f"SOURCE CONTEXT:\n{source_context}\n\n"
        "Return ONLY the complete fixed Python test file. No explanations."
    )
    raw = _chat(SUBAGENT_MODEL_ID, system_prompt, user_content)
    return {"kind": kind, "patch": _strip_code_fences(raw)}


def run_subagents_parallel(test_code: str, source_context: str) -> list:
    kinds = ["timing", "state", "randomness"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_subagent, kind, test_code, source_context): kind
            for kind in kinds
        }
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    return results