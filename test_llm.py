"""Phase 2 spike: prove the configured LLM provider actually answers.
Prints the resolved provider/model (config-must-be-live rule) and makes
exactly one tiny completion call. Not part of the package."""
import os
from dotenv import load_dotenv

load_dotenv()

provider = os.getenv("LLM_PROVIDER", "groq").lower()
print(f"[llm config] LLM_PROVIDER resolved to: {provider!r}")

if provider == "github":
    key = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_API_KEY")
    model = os.getenv("LLM_MODEL_SMART", "github/gpt-4o")
    print(f"[llm config] GITHUB_TOKEN present: {bool(key)}")
else:
    key = os.getenv("GROQ_API_KEY")
    model = "groq/llama-3.3-70b-versatile"
    print(f"[llm config] GROQ_API_KEY present: {bool(key)}")

print(f"[llm config] model: {model}")

import litellm

resp = litellm.completion(
    model=model,
    api_key=key,
    messages=[{"role": "user", "content": "Reply with exactly: PROVIDER_OK"}],
    max_tokens=10,
)
print("Response:", resp.choices[0].message.content)
print("Actual model used:", resp.model)
