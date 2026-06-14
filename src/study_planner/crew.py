from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from study_planner.llm_config import get_llms, ensure_litellm_patched
from study_planner.tools.pdf_tools import (
    list_input_files,
    read_document,
    search_document,
)


# ─── Crew ─────────────────────────────────────────────────────────────────────

@CrewBase
class StudyPlannerCrew:
    """5-agent study planner: three parallel analyses (profile, career,
    modules) feed a gap analysis and a semester-wise plan synthesis.

    LLM config and the litellm patch are resolved lazily in __init__ (not at
    import time) so importing this module has no global side effects — required
    for the multi-user worker, where many crews are built per process."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self):
        super().__init__()
        ensure_litellm_patched()
        self._llm_fast, self._llm_smart = get_llms()

    # ── Agents ──────────────────────────────────────────────────────────────

    @agent
    def profile_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["profile_analyst"],
            tools=[read_document, list_input_files],
            llm=self._llm_fast,
            verbose=True,
        )

    @agent
    def career_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["career_analyst"],
            tools=[read_document, list_input_files],
            llm=self._llm_fast,
            verbose=True,
        )

    @agent
    def module_curator(self) -> Agent:
        return Agent(
            config=self.agents_config["module_curator"],
            tools=[read_document, search_document],
            llm=self._llm_fast,
            verbose=True,
        )

    @agent
    def gap_analyst(self) -> Agent:
        # No tools: compares upstream outputs only — grounded synthesis.
        return Agent(
            config=self.agents_config["gap_analyst"],
            tools=[],
            llm=self._llm_smart,
            verbose=True,
        )

    @agent
    def study_planner(self) -> Agent:
        # No tools: plans strictly from the curator's module table.
        return Agent(
            config=self.agents_config["study_planner"],
            tools=[],
            llm=self._llm_smart,
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
