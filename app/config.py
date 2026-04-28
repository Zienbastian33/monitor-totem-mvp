from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    kiosk_url: str = "https://app.rdx.social"

    screenshot_interval_seconds: int = 900
    watchdog_interval_seconds: int = 30
    retention_interval_seconds: int = 3600
    offline_threshold_seconds: int = 900

    # primary | all | 1 | 2 | ...  (índice de mss; 1 = primario, 2 = secundario)
    screenshot_monitor: str = "primary"

    retention_hours_full: int = 24
    keep_daily_archive: bool = True

    host: str = "0.0.0.0"
    port: int = 8000

    chrome_path: str = ""
    chrome_user_data_dir: str = ""

    data_dir: str = ""

    totem_name: str = ""
    totem_location: str = "Sin especificar"

    display_timezone: str = "America/Santiago"

    ngrok_local_api: str = "http://localhost:4040"

    panel_username: str = "admin"
    panel_password: str = ""

    @property
    def data_path(self) -> Path:
        base = Path(self.data_dir) if self.data_dir else Path("data")
        return base.resolve()

    @property
    def screenshots_path(self) -> Path:
        return self.data_path / "screenshots"

    @property
    def db_path(self) -> Path:
        return self.data_path / "totems.db"

    @property
    def logs_path(self) -> Path:
        return self.data_path / "logs"

    @property
    def chrome_user_data_path(self) -> Path:
        return Path(self.chrome_user_data_dir) if self.chrome_user_data_dir else self.data_path / "chrome-profile"


settings = Settings()
