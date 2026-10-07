"""应用配置。所有可调项集中在这里，通过 .env 覆盖。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# codes/server/
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "沐晨课程管理系统"
    api_prefix: str = "/api"

    # 数据库：默认放在 codes/server/data/app.db
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'app.db').as_posix()}"
    sql_echo: bool = False

    # 认证
    jwt_secret: str = "dev-only-please-change-in-dotenv"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 天

    # 前端跨域（H5 开发时用）
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # 新生建档时直接送的课时（记一条 purchase 流水）。
    # 用户 2026-10-05 定的：新生默认 48 课时，省掉一次「建档完再去充课时」的操作。
    # 续费才需要手动充值。
    default_student_hours: float = 48
    default_student_hours_note: str = "新生默认课时"

    @property
    def data_dir(self) -> Path:
        return BASE_DIR / "data"

    def ensure_data_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
