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
limit, and falls back to Gemini when the primary provider is rate-limited), so
it is safe to share across concurrent crews in one process.

Fallback rationale: the free tiers have *daily* token caps (Groq: 100k TPD).
Once hit, no amount of in-request backoff recovers — the window is hours away.
A different provider (Gemini) is a separate quota pool, so on a rate-limit we
switch the call to `LLM_FALLBACK_MODEL` (default gemini/gemini-flash-latest) once,
using GEMINI_API_KEY, instead of failing the whole plan. Set GEMINI_API_KEY in
.env to arm it; leave it unset to keep the old retry-then-fail behaviour.
"""
from __future__ import annotations

import copy
import os
import re
import time
from functools import lru_cache

# Free-tier reality (measured 2026-06-15) — none is comfortable for a document-
# heavy 5-agent crew that makes dozens of calls; this split is the least-bad mix:
#   GitHub Models: ~8k tokens/request cap → too small to READ big docs, fine for
#                  the lighter synthesis pass.
#   Groq:          large context, ~100k tokens/DAY (TPD). Enough for ~1 full run/
#                  day; the best free fit for the token-hungry reading agents.
#   Gemini:        gemini-flash-latest = gemini-3.5-flash, only ~20 requests/DAY
#                  free — far too few to be the PRIMARY (a run needs dozens), but
#                  fine as an occasional fallback / a clean-boundary provider swap.
# "mixed" (default): reading on Groq (token budget), synthesis on GitHub gpt-4o,
# Gemini as the rate-limit fallback. For heavy/repeated use, set a paid key and
# point LLM_MODEL_FAST/SMART at it. "gemini" routes everything to Gemini (only
# viable on a paid Gemini tier).
_DEFAULTS = {
    "mixed":  ("groq/llama-3.3-70b-versatile", "github/gpt-4o"),
    "github": ("github/gpt-4o-mini", "github/gpt-4o"),
    "groq":   ("groq/llama-3.3-70b-versatile", "groq/llama-3.3-70b-versatile"),
    "gemini": ("gemini/gemini-flash-latest", "gemini/gemini-flash-latest"),
}

# Cross-provider fallback target when the primary provider (Groq) is rate-limited.
# Uses GitHub gpt-4o (GITHUB_TOKEN) — a separate quota pool from Groq.
# Override with LLM_FALLBACK_MODEL if needed.
_FALLBACK_MODEL = "github/gpt-4o"

_patched = False

# Provider-switch fallbacks fired in this process (for run manifests / debugging).
# Process-global: in a long-lived worker it accumulates across jobs; reset it per
# run via reset_fallback_events() when you want a clean per-run count.
_fallback_events: list[str] = []


def get_fallback_events() -> list[str]:
    """Return the cross-provider fallbacks fired since the last reset."""
    return list(_fallback_events)


def reset_fallback_events() -> None:
    """Clear the recorded fallback events (call at the start of a fresh run)."""
    _fallback_events.clear()


def _is_rate_limit(err: str) -> bool:
    return "rate_limit" in err.lower() or "429" in err


def is_daily_quota_error(err: str) -> bool:
    """True when the error is a DAILY free-tier cap (vs a per-minute throttle).

    A daily cap (Groq 'tokens per day (TPD)', Gemini 'RESOURCE_EXHAUSTED') resets
    hours away, so backoff is pointless and the whole service should pause and tell
    users to come back later. A per-minute cap ('tokens per minute / TPM') is NOT
    this — it clears in seconds and should keep backing off. Kept narrow so we never
    trigger a 24h pause on a transient throttle."""
    e = err.lower()
    if not ("rate" in e or "429" in e or "quota" in e or "resource_exhausted" in e):
        return False
    return any(s in e for s in (
        "per day", "tpd", "rpd", "resource_exhausted", "daily limit", "daily quota"))


def _is_context_overflow(err: str) -> bool:
    """The request exceeded the model's context window (e.g. GitHub gpt-4o's small
    free-tier cap on a big synthesis). Backoff can't fix it, but a provider with a
    larger window (Gemini) can — so it's a reason to fall back, not to retry."""
    e = err.lower()
    return any(s in e for s in (
        "context_length_exceeded", "context length", "maximum context",
        "too many tokens", "reduce the length", "string too long",
    ))


def _has_tool_call_history(messages) -> bool:
    """True if the conversation already contains tool-call turns.

    Switching LLM providers mid-tool-conversation is unsafe: providers attach
    incompatible function-call metadata. Concretely, Gemini rejects a history
    that contains another provider's tool calls — 'Function call is missing a
    thought_signature' (400). So we only switch providers at a clean boundary
    (no prior tool calls); mid-conversation we back off and retry the same one.
    """
    for m in messages or []:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
        tool_calls = (m.get("tool_calls") if isinstance(m, dict)
                      else getattr(m, "tool_calls", None))
        if role in ("tool", "function") or tool_calls:
            return True
    return False


def _is_transient(err: str) -> bool:
    """Transient server-side errors worth a retry (not a request defect): an
    overloaded/unavailable model (503/529), a 5xx, or a network timeout. These
    are common on free tiers under load — Gemini returns 503 'high demand' — and
    must not kill a multi-minute crew run on the first blip."""
    e = err.lower()
    return any(s in e for s in (
        "503", "500", "502", "504", "529", "overloaded", "unavailable",
        "service_unavailable", "serviceunavailable", "timeout", "timed out",
        "internalservererror", "internal server error",
    ))


def _is_bad_tool_format(err: str) -> bool:
    """True when Groq rejects a malformed tool call emitted by the model.

    llama-3.3-70b occasionally reverts to its pre-training function-call format
    (<function=name {args}>) instead of proper JSON tool calls. Groq parses the
    whole string as the tool name, finds no match in request.tools, and returns
    'tool_use_failed'. This is probabilistic model behaviour — retrying the same
    request usually produces the correct format."""
    e = err.lower()
    return "tool_use_failed" in e or "tool call validation failed" in e


def make_tool_schemas_strict(tools):
    """Set ``additionalProperties: false`` on every object in each tool's
    parameter schema.

    Why: Groq's function-calling validation *requires* it on every object
    ("`additionalProperties:false` must be set on every object") but crewai +
    newer litellm don't emit it, so the call 400s before it ever runs — a
    BadRequest, not a rate-limit, so the Gemini fallback can't help. Adding it is
    a no-op for providers that don't require it (the schemas here have no
    optional fields, so no strict-mode conflict). Returns a deep copy; never
    mutates the caller's objects.
    """
    if not tools:
        return tools

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                node.setdefault("additionalProperties", False)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    out = copy.deepcopy(tools)
    for t in out:
        params = t.get("function", {}).get("parameters") if isinstance(t, dict) else None
        if isinstance(params, dict):
            walk(params)
    return out


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
        # Groq rejects tool schemas lacking additionalProperties:false — patch
        # every tool's parameter schema so the call doesn't 400 (see helper).
        if kwargs.get("tools"):
            kwargs["tools"] = make_tool_schemas_strict(kwargs["tools"])
        # Resilience for free-tier flakiness. Two failure modes, two responses:
        #   * rate-limit (e.g. Groq's daily cap): switch ONCE to the Gemini
        #     fallback — a separate quota pool is the only thing that helps a
        #     *daily* limit; then back off.
        #   * transient 5xx / overload / timeout (Gemini returns 503 under load):
        #     just back off and retry — it clears in seconds.
        # Anything else (a real 4xx request defect) propagates immediately.
        # The provider switch is only safe at a clean boundary: once the
        # conversation has tool-call turns, swapping providers makes the new one
        # reject the other's tool metadata, so we retry the same provider instead.
        fell_back = False
        last_exc: Exception | None = None
        for attempt in range(6):
            try:
                return original(*args, **kwargs)
            except Exception as e:
                err = str(e)
                rate, transient = _is_rate_limit(err), _is_transient(err)
                overflow = _is_context_overflow(err)
                bad_tool = _is_bad_tool_format(err)
                if not (rate or transient or overflow or bad_tool):
                    raise
                if bad_tool:
                    print(f"[bad tool format] model emitted malformed tool call, retrying (attempt {attempt+1}/6)...")
                    last_exc = e
                    continue  # immediate retry — no sleep, no provider switch
                last_exc = e
                model = str(kwargs.get("model", ""))
                fallback_model = os.getenv("LLM_FALLBACK_MODEL", _FALLBACK_MODEL)
                fallback_key = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_API_KEY")
                # A rate-limit or a context-overflow is fixed by a different
                # provider (separate quota / larger window), not by waiting — but
                # only switch at a clean boundary (no cross-provider tool history).
                can_switch = ((rate or overflow) and fallback_key and not fell_back
                              and not model.startswith("github/")
                              and not _has_tool_call_history(kwargs.get("messages")))
                if can_switch:
                    why = "rate-limited" if rate else "context-overflow"
                    event = f"{model} {why} -> {fallback_model}"
                    print(f"[llm fallback] {event}")
                    _fallback_events.append(event)
                    kwargs["model"] = fallback_model
                    kwargs["api_key"] = fallback_key
                    fell_back = True
                    continue  # retry immediately on the fallback provider
                if overflow:
                    raise  # can't switch (tool history / no key) and backoff won't help
                # A DAILY cap we can't switch away from (no fallback left) won't
                # clear by waiting — the window is hours off. Fail fast so the job
                # fails immediately and the API can show "come back in 24h" instead
                # of burning ~5 minutes of pointless backoff per request.
                if is_daily_quota_error(err):
                    print(f"[daily quota exhausted] {model} -- failing fast")
                    raise
                mt = re.search(r"try again in ([\d.]+)s", err)
                wait = float(mt.group(1)) + 2 if mt else min(15 * (attempt + 1), 60)
                kind = "rate limit" if rate else "transient error"
                print(f"[{kind}] waiting {wait:.0f}s (attempt {attempt+1}/6)...")
                time.sleep(wait)
        # Exhausted retries — surface the real provider error, not a generic one.
        if last_exc is not None:
            raise last_exc
        return original(*args, **kwargs)

    litellm.completion = _patched_completion

    # Force crewai to route EVERY model through LiteLLM, not its native SDKs.
    # crewai 1.14 prefers a native provider for gemini/openai/... but (a) the
    # native Gemini path needs an extra google-genai dep and crashes without it
    # (it raises in _get_native_provider before the is_litellm guard), and (b) a
    # native provider bypasses the litellm.completion patch above, silently
    # disabling our fallback/retry/tool-schema fixes. Nulling the native lookup
    # makes crewai fall back to LiteLLM for all providers — one resilient path.
    try:
        from crewai import LLM as _CrewLLM
        _CrewLLM._get_native_provider = classmethod(lambda cls, provider: None)
    except Exception:
        pass

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
    elif model.startswith("gemini/"):
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError(f"model {model} needs GEMINI_API_KEY in .env")
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
    # is_litellm=True forces crewai down the LiteLLM path for EVERY provider
    # instead of its native SDKs. Two reasons: (1) native providers (e.g. Gemini's
    # google-genai) would need extra deps and, crucially, (2) they bypass our
    # litellm.completion patch — so the fallback / retry / tool-schema fixes would
    # silently not apply. Routing through LiteLLM keeps one resilient code path.
    llm_fast = LLM(model=fast_model, api_key=_key_for(fast_model),
                   temperature=0.2, is_litellm=True)
    llm_smart = LLM(model=smart_model, api_key=_key_for(smart_model),
                    temperature=0.2, is_litellm=True)
    return llm_fast, llm_smart
