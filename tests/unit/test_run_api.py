import os
from pathlib import Path

from app.core.config import ENV_FILE_PATH as APP_ENV_FILE_PATH
from app.core.config import REPO_ROOT as APP_REPO_ROOT
from app.core.config import Settings as AppSettings
from kabuhandan_hojo.core.config import ENV_FILE_PATH as MONITORING_ENV_FILE_PATH
from kabuhandan_hojo.core.config import REPO_ROOT as MONITORING_REPO_ROOT
from kabuhandan_hojo.core.config import Settings as MonitoringSettings
from scripts.run_api import main


def test_run_api_enables_mock(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    def fake_run(app_path: str, host: str, port: int, reload: bool, factory: bool) -> None:
        recorded["app_path"] = app_path
        recorded["host"] = host
        recorded["port"] = port
        recorded["reload"] = reload
        recorded["factory"] = factory

    monkeypatch.delenv("APP_USE_MOCK", raising=False)
    monkeypatch.setattr("scripts.run_api.uvicorn.run", fake_run)
    monkeypatch.chdir(Path(__file__).resolve().parents[2] / "scripts")

    exit_code = main(["--mock", "--host", "127.0.0.1", "--port", "9001", "--reload"])

    assert exit_code == 0
    assert os.environ["APP_USE_MOCK"] == "true"
    assert Path.cwd() == Path(__file__).resolve().parents[2]
    assert recorded == {
        "app_path": "app.main:create_app",
        "host": "127.0.0.1",
        "port": 9001,
        "reload": True,
        "factory": True,
    }


def test_settings_use_repo_root_env_file() -> None:
    assert Path(AppSettings.model_config["env_file"]) == APP_ENV_FILE_PATH
    assert Path(MonitoringSettings.model_config["env_file"]) == MONITORING_ENV_FILE_PATH
    assert APP_ENV_FILE_PATH.is_absolute()
    assert MONITORING_ENV_FILE_PATH.is_absolute()
    assert APP_ENV_FILE_PATH.parent == APP_REPO_ROOT
    assert MONITORING_ENV_FILE_PATH.parent == MONITORING_REPO_ROOT
