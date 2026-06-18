"""Verification gate for the Gemini cross-provider fallback in llm_config.

The free tiers cap *daily* tokens (Groq: 100k TPD). When that's hit, in-request
backoff can't recover — the reset is hours out. The patched litellm.completion
must instead switch the call to Gemini (a separate quota pool) exactly once.

These tests stub the underlying litellm.completion (`original`) so no network or
real key is needed: groq calls raise a rate-limit error, gemini calls succeed.
"""
import litellm
import pytest

import study_planner.llm_config as lc


def test_make_tool_schemas_strict_adds_additional_properties():
    """Groq requires additionalProperties:false on every object in a tool's
    parameter schema; the sanitizer must add it (and not mutate the input)."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_document",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "opts": {  # nested object must also get the flag
                            "type": "object",
                            "properties": {"chunk": {"type": "integer"}},
                        },
                    },
                    "required": ["file_path"],
                },
            },
        }
    ]
    out = lc.make_tool_schemas_strict(tools)

    params = out[0]["function"]["parameters"]
    assert params["additionalProperties"] is False
    assert params["properties"]["opts"]["additionalProperties"] is False
    # input untouched (deep copy)
    assert "additionalProperties" not in tools[0]["function"]["parameters"]


def test_make_tool_schemas_strict_preserves_existing_value():
    tools = [{"function": {"parameters": {"type": "object", "additionalProperties": True}}}]
    out = lc.make_tool_schemas_strict(tools)
    # setdefault: don't override an explicit choice
    assert out[0]["function"]["parameters"]["additionalProperties"] is True


@pytest.fixture
def patch_litellm(monkeypatch):
    """Install a fresh stub as litellm.completion, then arm the patch on top.

    Returns the call log so a test can assert which model/key each call used.
    The wrapper captures `original = litellm.completion` at patch time, so the
    stub must be set *before* ensure_litellm_patched() runs.
    """
    calls = []

    def make_stub(fail_models):
        def stub(*args, **kwargs):
            model = kwargs.get("model", "")
            calls.append({"model": model, "api_key": kwargs.get("api_key")})
            if any(model.startswith(p) for p in fail_models):
                raise Exception(
                    "litellm.RateLimitError: GroqException - rate_limit_exceeded "
                    "tokens per day (TPD): Limit 100000. try again in 1800s"
                )
            return f"OK:{model}"
        return stub

    # never sleep through a real backoff in a test
    monkeypatch.setattr(lc.time, "sleep", lambda _s: None)

    def arm(fail_models):
        monkeypatch.setattr(litellm, "completion", make_stub(fail_models))
        lc._patched = False  # force re-patch over the fresh stub
        lc.ensure_litellm_patched()

    yield arm, calls
    lc._patched = False  # leave the module unpatched for other tests


def test_falls_back_to_gemini_when_groq_rate_limited(patch_litellm, monkeypatch):
    arm, calls = patch_litellm
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key-123")
    arm(fail_models=["groq/"])

    result = litellm.completion(
        model="groq/llama-3.3-70b-versatile", messages=[], api_key="groq-key"
    )

    # Succeeded via the fallback, not the rate-limited primary.
    assert result == f"OK:{lc._FALLBACK_MODEL}"
    assert [c["model"] for c in calls] == [
        "groq/llama-3.3-70b-versatile",
        lc._FALLBACK_MODEL,
    ]
    # The fallback call used the Gemini key, not the Groq one.
    assert calls[1]["api_key"] == "gem-key-123"


def test_switches_provider_once_then_backs_off(patch_litellm, monkeypatch):
    """If Gemini also rate-limits, we switch providers exactly once (groq→gemini)
    and then back off+retry on gemini — never flip-flopping back to groq — and
    ultimately raise."""
    arm, calls = patch_litellm
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key-123")
    arm(fail_models=["groq/", "gemini/"])

    with pytest.raises(Exception):
        litellm.completion(
            model="groq/llama-3.3-70b-versatile", messages=[], api_key="groq-key"
        )

    # The single switch: groq tried once, then we never return to it.
    assert [c["model"] for c in calls].count("groq/llama-3.3-70b-versatile") == 1
    assert calls[0]["model"].startswith("groq/")
    assert all(c["model"].startswith("gemini/") for c in calls[1:])


def test_no_fallback_without_key_preserves_old_behaviour(patch_litellm, monkeypatch):
    """Unset GEMINI_API_KEY → never touch gemini; back off and raise as before."""
    arm, calls = patch_litellm
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    arm(fail_models=["groq/"])

    with pytest.raises(Exception):
        litellm.completion(
            model="groq/llama-3.3-70b-versatile", messages=[], api_key="groq-key"
        )

    assert all(c["model"].startswith("groq/") for c in calls)


def test_non_rate_limit_errors_are_not_retried(patch_litellm, monkeypatch):
    """A non-rate-limit error must propagate immediately (one call, no fallback)."""
    arm, calls = patch_litellm
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key-123")

    def stub(*args, **kwargs):
        calls.append({"model": kwargs.get("model", ""), "api_key": kwargs.get("api_key")})
        raise ValueError("bad request: malformed messages")

    monkeypatch.setattr(litellm, "completion", stub)
    lc._patched = False
    lc.ensure_litellm_patched()

    with pytest.raises(ValueError):
        litellm.completion(model="groq/llama-3.3-70b-versatile", messages=[])
    assert len(calls) == 1


def test_has_tool_call_history_detects_tool_turns():
    assert lc._has_tool_call_history([{"role": "assistant", "tool_calls": [{"id": "1"}]}])
    assert lc._has_tool_call_history([{"role": "tool", "content": "x"}])
    assert not lc._has_tool_call_history([{"role": "user", "content": "hi"}])
    assert not lc._has_tool_call_history([])
    assert not lc._has_tool_call_history(None)


def test_no_provider_switch_mid_tool_conversation(patch_litellm, monkeypatch):
    """With prior tool-call turns, a rate-limit must NOT switch to Gemini — the
    other provider rejects cross-provider tool metadata (thought_signature 400) —
    so we retry the same provider instead."""
    arm, calls = patch_litellm
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key-123")
    arm(fail_models=["groq/"])  # groq always rate-limits
    msgs = [
        {"role": "user", "content": "read the doc"},
        {"role": "assistant", "tool_calls": [{"id": "1", "function": {"name": "read"}}]},
        {"role": "tool", "content": "...file text..."},
    ]
    with pytest.raises(Exception):
        litellm.completion(model="groq/llama-3.3-70b-versatile", messages=msgs, api_key="k")
    # never switched to gemini despite the rate-limit
    assert calls, "expected at least one attempt"
    assert all(c["model"].startswith("groq/") for c in calls)


def test_transient_5xx_retried_then_succeeds(monkeypatch):
    """A 503 'overloaded' (e.g. Gemini under load) must be retried, not fatal."""
    monkeypatch.setattr(lc.time, "sleep", lambda _s: None)
    n = {"calls": 0}

    def stub(*a, **k):
        n["calls"] += 1
        if n["calls"] < 3:
            raise Exception("litellm.ServiceUnavailableError: GeminiException - "
                            '{"code":503,"message":"model is overloaded","status":"UNAVAILABLE"}')
        return "OK"

    monkeypatch.setattr(litellm, "completion", stub)
    lc._patched = False
    lc.ensure_litellm_patched()
    try:
        assert litellm.completion(model="gemini/gemini-flash-latest", messages=[]) == "OK"
        assert n["calls"] == 3
    finally:
        lc._patched = False


def test_exhausted_retries_surface_real_provider_error(monkeypatch):
    """If a transient error never clears, the real provider exception propagates
    (not a generic one), so the failure is diagnosable."""
    monkeypatch.setattr(lc.time, "sleep", lambda _s: None)

    def stub(*a, **k):
        raise Exception("503 model is overloaded, UNAVAILABLE")

    monkeypatch.setattr(litellm, "completion", stub)
    lc._patched = False
    lc.ensure_litellm_patched()
    try:
        with pytest.raises(Exception) as ei:
            litellm.completion(model="gemini/gemini-flash-latest", messages=[])
        assert "overloaded" in str(ei.value).lower()
    finally:
        lc._patched = False
