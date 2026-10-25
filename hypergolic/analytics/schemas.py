from pydantic import BaseModel


class AnalyticsSummary(BaseModel):
    total_sessions: int
    total_messages: int
    total_cost: float
    total_input_tokens: int
    total_output_tokens: int
    total_cache_write_tokens: int
    total_cache_read_tokens: int


class TimeseriesPoint(BaseModel):
    period: str
    sessions: int
    messages: int
    cost: float
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int


class ToolCount(BaseModel):
    tool_name: str
    count: int


class PerformanceCards(BaseModel):
    sandboxes: float
    idle_sandboxes: float
    sandbox_cores: float | None
    idle_cpu_share: float | None
    sandbox_memory_bytes: float | None
    throttled_cores: float | None
    harness_cores: float | None
    harness_rss_bytes: float | None
    loop_lag_p95_s: float | None


class SeriesPoint(BaseModel):
    at: float
    values: dict[str, float]


class SessionCost(BaseModel):
    session_id: str
    description: str | None
    state: str
    cpu_seconds: float
    memory_bytes: float | None


class ProgramCost(BaseModel):
    program: str
    runs: int
    wall_seconds: float
    cpu_seconds: float | None


class PerformanceReport(BaseModel):
    available: bool
    error: str | None = None
    cards: PerformanceCards | None = None
    cpu_by_container: list[SeriesPoint] = []
    memory_by_container: list[SeriesPoint] = []
    sessions: list[SessionCost] = []
    programs: list[ProgramCost] = []
