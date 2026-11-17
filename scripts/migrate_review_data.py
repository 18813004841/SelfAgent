"""复制历史代码检查数据；保留源数据，拒绝覆盖不一致的目标文件。"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import os
import stat
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def reject_links(path: Path) -> None:
    """拒绝路径自身及祖先中的链接/junction，避免复制越过目录边界。"""
    for part in (path, *path.parents):
        if not os.path.lexists(part):
            continue
        info = part.lstat()
        if part.is_symlink() or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise ValueError(f"不迁移链接路径: {part}")


def migrate(source: Path, destination: Path, apply: bool = False) -> list[dict]:
    reject_links(source.absolute())
    reject_links(destination.absolute())
    source, destination = source.resolve(strict=True), destination.resolve()
    if not source.is_dir():
        raise ValueError("源路径必须是目录")
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("源目录和目标目录不能相同或相互包含")
    records = []
    for path in sorted(source.rglob("*")):
        reject_links(path)
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        reject_links(target)
        checksum = digest(path)
        if target.exists() and (not target.is_file() or digest(target) != checksum):
            raise ValueError(f"目标冲突，未覆盖: {relative}")
        records.append({"path": relative.as_posix(), "sha256": checksum, "size": path.stat().st_size})
    if apply:
        for record in records:
            path = source / record["path"]
            target = destination / record["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(path, target)
            if digest(target) != record["sha256"]:
                raise RuntimeError(f"迁移校验失败: {record['path']}")
        manifest = {"source": str(source), "destination": str(destination), "files": records}
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        (destination / f"migration-{stamp}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


def backup_directory(source: Path, backup: Path) -> list[dict]:
    """Create a verified, additive backup before migration; never overwrite a backup."""
    reject_links(source.absolute())
    reject_links(backup.absolute())
    source = source.resolve(strict=True)
    backup = backup.resolve()
    if not source.is_dir() or backup == source or source in backup.parents:
        raise ValueError("备份路径必须是源目录之外的新目录")
    if backup.exists():
        raise ValueError(f"备份目标已存在，为避免覆盖而拒绝: {backup}")
    records = migrate(source, backup, apply=True)
    for record in records:
        if digest(backup / record["path"]) != record["sha256"]:
            raise RuntimeError(f"备份校验失败: {record['path']}")
    return records


def restore_backup(backup: Path, destination: Path) -> list[dict]:
    """Restore a backup into a new/empty destination using the same conflict checks."""
    reject_links(backup.absolute())
    reject_links(destination.absolute())
    backup = backup.resolve(strict=True)
    destination = destination.resolve()
    reject_links(backup)
    manifests = sorted(backup.glob("migration-*.json"))
    if len(manifests) != 1:
        raise ValueError("备份必须包含唯一校验清单")
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    for record in manifest["files"]:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("备份清单路径非法")
        path = backup / relative
        reject_links(path)
        if not path.is_file() or digest(path) != record["sha256"] or path.stat().st_size != record["size"]:
            raise ValueError(f"备份校验失败: {relative}")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("恢复目标必须不存在或为空目录")
    return migrate(backup, destination, apply=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path, help="应用迁移前创建并校验独立备份目录")
    parser.add_argument("--restore", action="store_true", help="将 source 备份恢复至不存在或为空的 destination；保留备份")
    args = parser.parse_args()
    if args.restore:
        if args.apply or args.backup:
            parser.error("--restore 不能与 --apply 或 --backup 同时使用")
        records = restore_backup(args.source, args.destination)
        print(f"restored and verified: {len(records)} files; backup retained")
        raise SystemExit(0)
    if args.backup and not args.apply:
        parser.error("--backup 需要 --apply")
    if args.backup:
        migrate(args.source, args.destination)  # 全量冲突预检后才创建备份
        backup_directory(args.source, args.backup)
    records = migrate(args.source, args.destination, args.apply)
    print(f"{'copied and verified' if args.apply else 'validated dry run'}: {len(records)} files; source retained")
