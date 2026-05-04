from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:dario_rag_2024@127.0.0.1:5432/dario_kb"
    rag_engine_url: str = "http://localhost:8420"
    orch_host: str = "0.0.0.0"
    orch_port: int = 8421
    orchestrator_dir: str = "C:/Users/barda/.claude/orchestrator"
    skills_dir: str = "C:/Users/barda/.claude/skills"
    log_level: str = "INFO"
    micro_pulse_seconds: int = 300
    session_pulse_seconds: int = 1800

    model_config = {"env_file": str(Path(__file__).parent.parent / "config" / ".env")}

    @property
    def orchestrator_path(self) -> Path:
        return Path(self.orchestrator_dir)

    @property
    def skills_path(self) -> Path:
        return Path(self.skills_dir)

    @property
    def tasks_active_path(self) -> Path:
        return self.orchestrator_path / "tasks" / "active"

    @property
    def tasks_done_path(self) -> Path:
        return self.orchestrator_path / "tasks" / "done"

    @property
    def budgets_path(self) -> Path:
        return self.orchestrator_path / "budgets"


settings = Settings()
