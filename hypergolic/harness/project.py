import inspect
from typing import Any, Callable, Coroutine

from pydantic import BaseModel, Field, PrivateAttr, model_validator

from hypergolic.gates.model import Gate, LandMode, OnStaleBase
from hypergolic.harness.primitives.bundles import Skill, Workflow, validate_prompt_exclusivity
from hypergolic.harness.primitives.tool import Tool, ToolRegistryMixin
from hypergolic.sandbox.model.sandbox import DEFAULT_SANDBOX_ID, ProjectSandbox, default_sandbox
from hypergolic.schemas import Session

SeedWorkspaceFn = Callable[[Session], Coroutine[Any, Any, None]]


class Project(ToolRegistryMixin, BaseModel):
    id: str
    name: str
    description: str
    git_root: str
    prompt_path: str | None = None
    prompt: str | None = None
    prompt_fn: Callable[..., str] | None = None
    tools: list[Tool] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    workflows: list[Workflow] = Field(default_factory=list)
    seed_workspace: SeedWorkspaceFn | None = None
    sandbox: ProjectSandbox | None = None
    # Shell command run inside the project sandbox (first declared container, at the
    # workspace mount) before every `git commit`; a nonzero exit blocks the
    # commit. Fail-closed: if set but the sandbox is unavailable, commits are
    # refused rather than allowed through unchecked.
    pre_commit: str | None = None
    # Landing-gate pipeline for `git push origin HEAD:<branch>` (see
    # hypergolic.gates). None means the default: [UserApproval()] — every
    # /app land needs the human; /shared lands ungated. The harness pipeline
    # is configured at the App level only, never per project.
    merge_gates: list[Gate] | None = None
    on_stale_base: OnStaleBase = "land"
    land_mode: LandMode = "squash"
    # Sandbox resolution state. These are PrivateAttrs, so they are NOT carried
    # across ``model_copy``/re-validation — they reset to their defaults on a
    # fresh instance. That is fine here: Projects are constructed once in
    # ``main.py`` and registered on the App; we never copy a live one. The
    # ``_default_*`` caches simply re-populate lazily on first access.
    _sandbox_configured: bool = PrivateAttr(default=False)
    _default_sandbox: ProjectSandbox | None = PrivateAttr(default=None)
    _default_cmd_tool: Tool | None = PrivateAttr(default=None)

    model_config = {"arbitrary_types_allowed": True}

    _validate_prompt = model_validator(mode="after")(validate_prompt_exclusivity)

    @model_validator(mode="after")
    def _validate_seed_workspace_is_async(self) -> "Project":
        if self.seed_workspace is not None and not inspect.iscoroutinefunction(self.seed_workspace):
            fn_name = getattr(self.seed_workspace, "__name__", "<unknown>")
            raise ValueError(
                f"Project '{self.id}' seed_workspace must be async. "
                f"Change 'def {fn_name}(...)' to 'async def {fn_name}(...)'."
            )
        return self

    @property
    def path(self) -> str:
        """Filesystem root of the project's git repo (alias for ``git_root``)."""
        return self.git_root

    def register_skill(self, skill: Skill) -> None:
        self.skills.append(skill)

    def register_skills(self, skills: list[Skill]) -> None:
        self.skills.extend(skills)

    def register_workflow(self, workflow: Workflow) -> None:
        self.workflows.append(workflow)

    def register_workflows(self, workflows: list[Workflow]) -> None:
        self.workflows.extend(workflows)

    def configure_sandbox(self, sandbox: ProjectSandbox | None) -> None:
        """Attach a sandbox to this project (or opt out with ``None``).

        Three outcomes drive whether the agent gets a ``cmd`` tool:

        - A :class:`ProjectSandbox` — the agent runs shell commands inside it,
          honoring its egress configuration. The per-project ``cmd`` tool
          exposes a typed ``container`` selector when the sandbox has more than
          one container.
        - ``None`` — the project explicitly opts out; no ``cmd`` tool appears
          (e.g. a non-coding project that must not run shell commands).
        - Never calling this leaves the project on the default sandbox
          (:func:`hypergolic.sandbox.model.default_sandbox`, egress denied).
        """
        if self._sandbox_configured:
            raise ValueError(f"Project '{self.id}' already has a sandbox configured")

        if sandbox is not None and sandbox.id == DEFAULT_SANDBOX_ID:
            raise ValueError(
                f"Sandbox id {DEFAULT_SANDBOX_ID!r} is reserved for the built-in "
                "default sandbox; give your project's sandbox a unique id"
            )

        self.sandbox = sandbox
        self._sandbox_configured = True

        if sandbox is None:
            return

        from hypergolic.sandbox.tool import make_project_sandbox_tool

        self.register_tool(make_project_sandbox_tool(sandbox))

    @property
    def resolved_sandbox(self) -> ProjectSandbox | None:
        """The sandbox the agent actually runs in for this project.

        Returns ``None`` only when the project explicitly opted out. An
        unconfigured project resolves to a per-project default sandbox,
        allocated once and reused thereafter so callers on the hot path
        (``build_tools`` every turn) don't re-allocate it. The compose file is
        materialized lazily by the ``cmd`` tool's run path, not here.
        """
        if self._sandbox_configured:
            return self.sandbox

        if self._default_sandbox is None:
            self._default_sandbox = default_sandbox()
        return self._default_sandbox

    def default_cmd_tool(self) -> Tool | None:
        """The ``cmd`` tool for an unconfigured project's default sandbox.

        Built once and memoized so the per-turn ``build_tools`` path does no
        work after the first call. Returns ``None`` for a configured project
        (which already owns a ``cmd`` from :meth:`configure_sandbox`) or one
        that opted out via ``configure_sandbox(None)``.
        """
        if self._sandbox_configured:
            return None

        if self._default_cmd_tool is None:

            sandbox = self.resolved_sandbox
            assert sandbox is not None  # unconfigured ⇒ always the default
            from hypergolic.sandbox.tool import make_project_sandbox_tool

            self._default_cmd_tool = make_project_sandbox_tool(sandbox)
        return self._default_cmd_tool
