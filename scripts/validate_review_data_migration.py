"""验证代码检查历史数据迁移的 dry-run、重复执行和冲突保护。"""
import tempfile
from pathlib import Path
import sys
import subprocess
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from migrate_review_data import migrate, backup_directory, restore_backup, digest


def verify_raw_path_preflight():
    # A rejected original path must never reach resolve(), which removes links.
    for operation in (backup_directory, restore_backup):
        original = Path("unresolved-link")
        with patch("migrate_review_data.reject_links", side_effect=ValueError("link rejected")) as reject:
            try:
                operation(original, Path("destination"))
            except ValueError as exc:
                assert str(exc) == "link rejected"
            else:
                raise AssertionError("raw path preflight was bypassed")
            reject.assert_called_once_with(original.absolute())

def main():
    verify_raw_path_preflight()
    with tempfile.TemporaryDirectory(prefix="selfagent-migration-") as root:
        base = Path(root); source = base / "old"; dest = base / "new"
        (source / "reports").mkdir(parents=True)
        (source / "reports" / "one.json").write_text('{"ok":true}', encoding="utf-8")
        assert len(migrate(source, dest)) == 1
        migrate(source, dest, apply=True)
        migrate(source, dest, apply=True)
        assert (dest / "reports" / "one.json").read_text(encoding="utf-8") == '{"ok":true}'
        (dest / "reports" / "one.json").write_text("conflict", encoding="utf-8")
        (source / "aaa-new.txt").write_text("must not copy before preflight completes", encoding="utf-8")
        try:
            migrate(source, dest, apply=True)
        except ValueError as exc:
            assert "目标冲突" in str(exc)
        else:
            raise AssertionError("conflicting destination was accepted")
        assert (source / "reports" / "one.json").is_file()
        assert not (dest / "aaa-new.txt").exists()
        assert (dest / "reports" / "one.json").read_text(encoding="utf-8") == "conflict"
        # 迁移前备份和恢复演练：备份不可覆盖，恢复后逐文件校验。
        backup = base / "backup"
        backup_directory(source, backup)
        cli_restore = base / "cli-restored"
        command = [sys.executable, str(Path(__file__).with_name("migrate_review_data.py")), str(backup), str(cli_restore), "--restore"]
        subprocess.run(command, check=True, capture_output=True, text=True)
        assert digest(cli_restore / "reports" / "one.json") == digest(source / "reports" / "one.json")
        rejected = subprocess.run([*command, "--apply"], capture_output=True, text=True)
        assert rejected.returncode == 2
        restore = base / "restored"
        restore_backup(backup, restore)
        assert digest(restore / "reports" / "one.json") == digest(backup / "reports" / "one.json")
        try:
            backup_directory(dest, backup)
        except ValueError as exc:
            assert "已存在" in str(exc)
        else:
            raise AssertionError("existing backup was overwritten")
        (backup / "reports" / "one.json").write_text("corrupted", encoding="utf-8")
        try:
            restore_backup(backup, base / "corrupt-restore")
        except ValueError as exc:
            assert "备份校验失败" in str(exc)
        else:
            raise AssertionError("corrupted backup accepted")
        assert not (base / "corrupt-restore").exists()
    print("review data migration validation passed")

if __name__ == "__main__":
    main()
