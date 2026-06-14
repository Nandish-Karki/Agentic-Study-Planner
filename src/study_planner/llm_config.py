"""
LLM configuration + litellm patching — resolved lazily, never at import time.

Why this exists (BUILD_PLAN §3.4, engine debt #1 and #2):
  * The old code monkeypatched `litellm.completion` and built two `LLM` objects
    at module import. That meant *importing* the crew mutated global state and
    read env once — a leak into any importer and a problem for the multi-user
    worker, which builds many crews per process.
  * Here the patch is applied once, guarded by a flag (idempotent), and the LLMs
    are built on first use and cached. Importing this module does nothing.

The patch itself is stateless (strips a stray message field + retries on rate
limit), so it is safe to share across concurrent crews in one process.
"""
from __future__ import annotations

import os
import re
import time
from functools import lru_cache

# Free-tier limits force a split strategy:
#   GitHub Models: ~8k tokens/request cap → too small for document-reading agents
#   Groq:          larger context, daily budget
# "mixed" (default): tool agents on Groq (big contexts), synthesis on GitHub gpt-4o.
_DEFAULTS = {
    "mixed":  ("groq/llama-3.3-70b-versatile", "github/gpt-4o"),
    "github": ("github/gpt-4o-mini", "github/gpt-4o"),
    "groq":   ("groq/llama-3.3-70b-versatile", "groq/llama-3.3-70b-versatile"),
}

_patched = False


def ensure_litellm_patched() -> None:
    """Apply the litellm.completion patch exactly once (idempotent)."""
    global _patched
    if _patched:
        return
    import litellm

    original = litellm.completion

    def _patched_completion(*args, **kwargs):
        # CrewAI 1.14.x leaks an internal `cache_breakpoint` message property
        # that some providers reject — strip it.
        for m in kwargs.get("messages") or []:
            if isinstance(m, dict):
                m.pop("cache_breakpoint", None)
        # Retry on rate-limit using the wait the provider suggests.
        for attempt in range(5):
            try:
                return original(*args, **kwargs)
            except Exception as e:
                err = str(e)
                if "rate_limit" in err.lower() or "429" in err:
                    mt = re.search(r"try again in ([\d.]+)s", err)
                    wait = float(mt.group(1)) + 2 if mt else 20 * (attempt + 1)
                    print(f"[rate limit] waiting {wait:.0f}s (attempt {attempt+1}/5)…")
                    time.sleep(wait)
                else:
                    raise
        return original(*args, **kwargs)

    litellm.completion = _patched_completion
    _patched = True


def _key_for(model: str) -> str:
    """Resolve the API key from the model's provider prefix."""
    if model.startswith("github/"):
        key = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_API_KEY")
        if not key:
            raise ValueError(f"model {model} needs GITHUB_TOKEN in .env")
    elif model.startswith("groq/"):
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise ValueError(f"model {model} needs GROQ_API_KEY in .env")
    else:
        raise ValueError(f"unsupported provider prefix in model: {model}")
    return key


def resolve_models() -> tuple[str, str]:
    """(fast_model, smart_model) from env, validated. No object construction."""
    provider = os.getenv("LLM_PROVIDER", "mixed").lower()
    if provider not in _DEFAULTS:
        raise ValueError(
            f"LLM_PROVIDER must be one of {list(_DEFAULTS)} — got {provider!r}")
    fast = os.getenv("LLM_MODEL_FAST", _DEFAULTS[provider][0])
    smart = os.getenv("LLM_MODEL_SMART", _DEFAULTS[provider][1])
    return fast, smart


@lru_cache(maxsize=1)
def get_llms():
    """Build (llm_fast, llm_smart) once and cache. Reads env on first call."""
    from crewai import LLM

    fast_model, smart_model = resolve_models()
    print(f"[llm config] fast={fast_model}  smart={smart_model}")
    llm_fast = LLM(model=fast_model, api_key=_key_for(fast_model), temperature=0.2)
    llm_smart = LLM(model=smart_model, api_key=_key_for(smart_model), temperature=0.2)
    return llm_fast, llm_smart
