"""Transactional email sender tests (Workstream 4 — SMTP launch blocker).

Mocks smtplib so no network/provider is needed: covers the disabled no-op, the
STARTTLS path, the implicit-SSL path, and graceful failure.
"""
import asyncio
import types

from study_planner.api import email


def _settings(**kw):
    base = dict(smtp_host="smtp.example.com", smtp_port=587, smtp_user="user",
                smtp_password="pw", smtp_from="Study Planner <no-reply@x.com>",
                smtp_starttls=False, smtp_ssl=False, email_enabled=True)
    base.update(kw)
    return types.SimpleNamespace(**base)


def _run(coro):
    return asyncio.run(coro)


def test_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(email, "settings", _settings(email_enabled=False))
    assert _run(email._send("a@b.c", "s", "t", "<p>h</p>")) is False


def test_starttls_path(monkeypatch):
    seen = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=10):
            seen["host"], seen["port"] = host, port
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): seen["starttls"] = True
        def login(self, u, p): seen["login"] = (u, p)
        def send_message(self, m): seen["sent"] = True

    monkeypatch.setattr(email, "settings", _settings(smtp_starttls=True))
    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)
    assert _run(email._send("a@b.c", "s", "t", "<p>h</p>")) is True
    assert seen.get("starttls") and seen.get("sent") and seen["login"] == ("user", "pw")


def test_implicit_ssl_path(monkeypatch):
    seen = {}

    class FakeSSL:
        def __init__(self, host, port, timeout=10, context=None):
            seen["port"] = port
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, u, p): seen["login"] = True
        def send_message(self, m): seen["sent"] = True

    monkeypatch.setattr(email, "settings", _settings(smtp_ssl=True, smtp_port=465))
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", FakeSSL)
    assert _run(email._send("a@b.c", "s", "t", "<p>h</p>")) is True
    assert seen.get("sent") and seen.get("port") == 465


def test_failure_returns_false_not_raises(monkeypatch):
    def _boom(*a, **k):
        raise OSError("smtp down")

    monkeypatch.setattr(email, "settings", _settings())
    monkeypatch.setattr(email.smtplib, "SMTP", _boom)
    assert _run(email._send("a@b.c", "s", "t", "<p>h</p>")) is False


def test_sentry_noop_without_dsn(monkeypatch):
    # No SENTRY_DSN -> init is a graceful no-op (never breaks boot).
    from study_planner.api import observability
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    observability._done = False
    assert observability.init_sentry("api") is False
