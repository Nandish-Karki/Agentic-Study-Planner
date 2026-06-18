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
        # Do NOT call super().__init__(): @CrewBase (crewai 1.14.x) rebuilds this
        # class through a metaclass, so the class captured by zero-arg super() is a
        # sibling of the real instance class, not a parent — calling it raises
        # "super(type, obj): obj must be an instance or subtype of type". CrewBase
        # runs its own init in the metaclass __call__ after this method returns.
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
        # No tools: plans strictly from the Python-curated available_modules table.
        # Uses llm_fast (Groq, large context) rather than llm_smart (GitHub gpt-4o,
        # ~8k limit) — the planner's task is constraint-following within a pre-filtered
        # list, where large context and reliable instruction-following matter more than
        # general reasoning ability.
        return Agent(
            config=self.agents_config["study_planner"],
            tools=[],
            llm=self._llm_fast,
            verbose=True,
        )

    # ── Tasks ───────────────────────────────────────────────────────────────

    @task
    def plan_task_v2(self) -> Task:
        return Task(config=self.tasks_config["plan_task_v2"])

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

    def phase1_crew(self, include_modules: bool = True) -> Crew:
        """Profile, career, modules, gap — outputs fed to Python normalization.

        When the handbook was parsed deterministically (ingest.handbook_parser),
        the LLM module_curator is skipped (`include_modules=False`) — it can't read
        a 900-page handbook anyway, and the parser is more reliable. gap_task only
        depends on profile+career, so dropping modules is safe."""
        agents = [self.profile_analyst(), self.career_analyst()]
        tasks = [self.profile_task(), self.career_task()]
        if include_modules:
            agents.append(self.module_curator())
            tasks.append(self.modules_task())
        agents.append(self.gap_analyst())
        tasks.append(self.gap_task())
        return Crew(agents=agents, tasks=tasks, process=Process.sequential,
                    verbose=True)

    def phase2_crew(self) -> Crew:
        """Planner only — all inputs arrive as Python-curated description variables."""
        return Crew(
            agents=[self.study_planner()],
            tasks=[self.plan_task_v2()],
            process=Process.sequential,
            verbose=True,
        )
