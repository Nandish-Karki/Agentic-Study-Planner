"""
Preflight check — verifies the environment before a real run.

Usage:  python -m study_planner.check [data-dir]     (default: sample_data)

Checks, in order: Python version, dependencies, .env + provider config,
a live 1-token LLM call per configured provider, and the input documents.
Every failure prints a specific FIX instruction. Exit code 0 = ready.
"""
import os
import pathlib
import sys

FAILURES = []


def report(ok: bool, label: str, detail: str = "", fix: str = ""):
    mark = "[ OK ]" if ok else "[FAIL]"
    print(f"{mark} {label}" + (f" - {detail}" if detail else ""))
    if not ok:
        if fix:
            print(f"       FIX: {fix}")
        FAILURES.append(label)
    return ok


def check_python():
    v = sys.version_info
    report(
        (3, 10) <= (v.major, v.minor) < (3, 14),
        "Python version",
        f"{v.major}.{v.minor}.{v.micro}",
        "Use Python 3.10-3.13 (CrewAI deps have no 3.14 wheels on Windows). "
        "Install 3.10 and recreate the venv: py -3.10 -m venv .venv",
    )


def check_deps():
    for mod in ("crewai", "litellm", "pypdf", "dotenv"):
        try:
            __import__(mod)
            report(True, f"dependency: {mod}")
        except ImportError:
            report(False, f"dependency: {mod}", "not importable",
                   "run setup.ps1 / setup.sh, or: .venv/Scripts/pip install -e .")


def check_env() -> list[str]:
    """Validate .env and return the list of models that will be used."""
    if not pathlib.Path(".env").exists():
        report(False, ".env file", "missing",
               "copy .env.example to .env and add your token")
        return []
    from dotenv import load_dotenv
    load_dotenv()

    # keep in sync with crew.py _defaults
    defaults = {
        "mixed":  ("groq/llama-3.3-70b-versatile", "github/gpt-4o"),
        "github": ("github/gpt-4o-mini", "github/gpt-4o"),
        "groq":   ("groq/llama-3.3-70b-versatile", "groq/llama-3.3-70b-versatile"),
    }
    provider = os.getenv("LLM_PROVIDER", "mixed").lower()
    if not report(provider in defaults, "LLM_PROVIDER", provider,
                  f"set LLM_PROVIDER in .env to one of {list(defaults)}"):
        return []

    models = [
        os.getenv("LLM_MODEL_FAST", defaults[provider][0]),
        os.getenv("LLM_MODEL_SMART", defaults[provider][1]),
    ]
    for prefix, var, hint in (
        ("github/", "GITHUB_TOKEN",
         "create a token at github.com/settings/personal-access-tokens "
         "with 'Models: read' permission, put it in .env"),
        ("groq/", "GROQ_API_KEY",
         "create a free key at console.groq.com/keys, put it in .env"),
    ):
        if any(m.startswith(prefix) for m in models):
            report(bool(os.getenv(var)), f"key present: {var}",
                   f"needed for {prefix}* models", hint)
    return models


def check_llm_live(models: list[str]):
    """One 1-token completion per distinct provider — proves the token works."""
    import litellm
    keys = {"github/": os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_API_KEY"),
            "groq/": os.getenv("GROQ_API_KEY")}
    tried = set()
    for model in models:
        prefix = model.split("/")[0] + "/"
        if prefix in tried or not keys.get(prefix):
            continue
        tried.add(prefix)
        try:
            litellm.completion(
                model=model, api_key=keys[prefix], max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            report(True, f"live LLM call: {model}")
        except Exception as e:
            msg = str(e).split("\n")[0][:120]
            report(False, f"live LLM call: {model}", msg,
                   "token invalid/expired, or missing 'Models: read' scope "
                   "(GitHub) / wrong key (Groq) - regenerate and update .env")


def check_data(data_dir: str):
    from pypdf import PdfReader
    d = pathlib.Path(data_dir)
    if not report(d.exists(), f"input folder: {d}", "",
                  "pass an existing folder, e.g.: python -m study_planner.check sample_data"):
        return
    for name in ("cv.pdf", "transcript.pdf", "career.pdf", "module_handbook.pdf"):
        f = d / name
        if not report(f.exists(), f"input file: {f.name}", "",
                      f"put {name} into {d} (see data/README.md; or use sample_data)"):
            continue
        try:
            text = "".join(p.extract_text() or "" for p in PdfReader(f).pages)
            report(len(text) > 50, f"text extractable: {f.name}",
                   f"{len(text)} chars",
                   "PDF has no text layer (scanned image?) - export a text-based PDF")
        except Exception as e:
            report(False, f"text extractable: {f.name}", str(e)[:80],
                   "file is corrupt or not a PDF")


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "sample_data"
    print(f"\nAgentic Study Planner - preflight check (inputs: {data_dir})\n")
    check_python()
    check_deps()
    if "crewai" not in FAILURES:
        models = check_env()
        if models:
            check_llm_live(models)
    check_data(data_dir)
    print()
    if FAILURES:
        print(f"NOT READY - {len(FAILURES)} problem(s) above. Fix and re-run.")
        sys.exit(1)
    print("READY - run:  python -m study_planner.main " + data_dir)


if __name__ == "__main__":
    main()
