import os
import re
import time
import litellm
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task

from study_planner.tools.pdf_tools import (
    list_input_files,
    read_document,
    search_document,
)

# ─── LiteLLM patches (ported from agent-workshop, proven 2026-06-11) ──────────
# 1. CrewAI 1.14.x leaks an internal `cache_breakpoint` message property that
#    some providers reject — strip it.
# 2. Retry on rate-limit using the wait time the provider suggests.
_original_completion = litellm.completion


def _patched_completion(*args, **kwargs):
    for m in kwargs.get("messages") or []:
        if isinstance(m, dict):
            m.pop("cache_breakpoint", None)

    for attempt in range(5):
        try:
            return _original_completion(*args, **kwargs)
        except Exception as e:
            err = str(e)
            if "rate_limit" in err.lower() or "429" in err:
                m = re.search(r"try again in ([\d.]+)s", err)
                wait = float(m.group(1)) + 2 if m else 20 * (attempt + 1)
                print(f"[rate limit] waiting {wait:.0f}s (attempt {attempt+1}/5)…")
                time.sleep(wait)
            else:
                raise
    return _original_completion(*args, **kwargs)


litellm.completion = _patched_completion

# ─── LLM provider switch (LLM_PROVIDER in .env: github | groq) ────────────────
_provider = os.getenv("LLM_PROVIDER", "groq").lower()

if _provider == "github":
    _key = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_API_KEY")
    if not _key:
        raise ValueError("LLM_PROVIDER=github but GITHUB_TOKEN is not set in .env")
    _fast_model = os.getenv("LLM_MODEL_FAST", "github/gpt-4o-mini")
    _smart_model = os.getenv("LLM_MODEL_SMART", "github/gpt-4o")
else:
    _key = os.getenv("GROQ_API_KEY")
    if not _key:
        raise ValueError("LLM_PROVIDER=groq but GROQ_API_KEY is not set in .env")
    _fast_model = os.getenv("LLM_MODEL_FAST", "groq/llama-3.3-70b-versatile")
    _smart_model = os.getenv("LLM_MODEL_SMART", "groq/llama-3.3-70b-versatile")

print(f"[llm config] provider={_provider}  fast={_fast_model}  smart={_smart_model}")

llm_fast = LLM(model=_fast_model, api_key=_key, temperature=0.2)
llm_smart = LLM(model=_smart_model, api_key=_key, temperature=0.2)


# ─── Crew ─────────────────────────────────────────────────────────────────────

@CrewBase
class StudyPlannerCrew:
    """5-agent study planner: three parallel analyses (profile, career,
    modules) feed a gap analysis and a semester-wise plan synthesis."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # ── Agents ──────────────────────────────────────────────────────────────

    @agent
    def profile_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["profile_analyst"],
            tools=[read_document, list_input_files],
            llm=llm_fast,
            verbose=True,
        )

    @agent
    def career_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["career_analyst"],
            tools=[read_document, list_input_files],
            llm=llm_fast,
            verbose=True,
        )

    @agent
    def module_curator(self) -> Agent:
        return Agent(
            config=self.agents_config["module_curator"],
            tools=[read_document, search_document],
            llm=llm_fast,
            verbose=True,
        )

    @agent
    def gap_analyst(self) -> Agent:
        # No tools: compares upstream outputs only — grounded synthesis.
        return Agent(
            config=self.agents_config["gap_analyst"],
            tools=[],
            llm=llm_smart,
            verbose=True,
        )

    @agent
    def study_planner(self) -> Agent:
        # No tools: plans strictly from the curator's module table.
        return Agent(
            config=self.agents_config["study_planner"],
            tools=[],
            llm=llm_smart,
            verbose=True,
        )

    # ── Tasks ───────────────────────────────────────────────────────────────

    @task
    def profile_task(self) -> Task:
        return Task(config=self.tasks_config["profile_task"])

    @task
    def career_task(self) -> Task:
        return Task(config=self.tasks_config["career_task"])

    @task
    def modules_task(self) -> Task:
        return Task(config=self.tasks_config["modules_task"])

    @task
    def gap_task(self) -> Task:
        return Task(config=self.tasks_config["gap_task"])

    @task
    def plan_task(self) -> Task:
        return Task(config=self.tasks_config["plan_task"])

    # ── Crew ────────────────────────────────────────────────────────────────

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
