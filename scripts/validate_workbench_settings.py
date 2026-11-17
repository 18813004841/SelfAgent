"""验证工作台配置优先级、类型归一化和目录可写性。"""
import json
import os
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="selfagent-settings-") as root:
        os.environ["LOCALAPPDATA"] = root
        os.environ["WORKBENCH_LOG_LEVEL"] = "DEBUG"
        os.environ["WORKBENCH_DEBUG_LOG"] = "true"
        os.environ["WORKBENCH_OUTPUT_DIR"] = str(Path(root) / "env-output")
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workbench/machine-dashboard-server/src"))
        from core.settings import load_local_settings
        values = load_local_settings()
        assert values["log_level"] == "DEBUG"
        assert values["debug_log"] is True
        assert Path(values["output_dir"]).is_dir()
        from core.settings import SETTING_PATH
        persisted = json.loads(SETTING_PATH.read_text(encoding="utf-8"))
        assert persisted["log_level"] == "INFO"
        assert persisted["output_dir"] != values["output_dir"]
        os.environ.pop("WORKBENCH_LOG_PATH", None)
        defaults = load_local_settings()
        assert Path(defaults["log_path"]) == Path(root) / "LocalWorkbench" / "output" / "logs"
        import core.settings as settings_module
        settings_module.SETTING_PATH = None
        legacy_root = Path(root) / "legacy"
        os.environ["LOCALAPPDATA"] = str(legacy_root)
        legacy = legacy_root / "LocalWorkbench" / "config" / "logs"
        legacy.mkdir(parents=True)
        (legacy / "old.log").write_text("keep", encoding="utf-8")
        config = legacy.parent / "local_setting.json"
        config.write_text(json.dumps({"log_level": "INFO", "debug_log": False, "log_path": str(legacy)}), encoding="utf-8")
        migrated = load_local_settings()
        assert (Path(migrated["log_path"]) / "old.log").read_text(encoding="utf-8") == "keep"
        assert (legacy / "old.log").is_file()
        os.environ["WORKBENCH_LOG_LEVEL"] = "INVALID"
        try:
            load_local_settings()
        except ValueError:
            pass
        else:
            raise AssertionError("invalid log level must fail")
        print("workbench settings validation passed")


if __name__ == "__main__":
    main()
