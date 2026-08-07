"""Migrate legacy takeout-named settings to the neutral printer-relay names.

Usage from the project root::

    python tools/migrate_printer_relay_config.py
    python tools/migrate_printer_relay_config.py --data C:\\path\\to\\data
    python tools/migrate_printer_relay_config.py --dry-run

Configuration files are renamed to ``printer_relay.json`` and migrated.  The
old runtime artifacts (status/control/jobs/capture) are renamed as well, and
capture sample stems change from ``takeout_`` to ``printer_relay_``.
"""
from __future__ import print_function

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime


EXPLICIT_RENAMES = {
    "takeout_interceptor_enabled": "printer_relay_enabled",
    "takeout_proxy_port": "printer_relay_port",
    "takeout_proxy_queue_name": "printer_relay_queue_name",
    "takeout_proxy_mode_version": "printer_relay_mode_version",
    "takeout_relay_mode": "printer_relay_mode",
    "takeout_relay_mode_policy": "printer_relay_mode_policy",
    "takeout_relay_last_check_at": "printer_relay_last_check_at",
    "takeout_relay_last_success_at": "printer_relay_last_success_at",
    "takeout_relay_last_error": "printer_relay_last_error",
    "takeout_relay_last_identification": "printer_relay_last_identification",
    "takeout_relay_payment_required": "printer_relay_payment_required",
    # Correct a first-pass migration that used the mechanical prefix rule.
    "printer_relay_relay_mode": "printer_relay_mode",
    "printer_relay_relay_mode_policy": "printer_relay_mode_policy",
    "printer_relay_relay_last_check_at": "printer_relay_last_check_at",
    "printer_relay_relay_last_success_at": "printer_relay_last_success_at",
    "printer_relay_relay_last_error": "printer_relay_last_error",
    "printer_relay_relay_last_identification": "printer_relay_last_identification",
    "printer_relay_relay_payment_required": "printer_relay_payment_required",
    "printer_relay_interceptor_enabled": "printer_relay_enabled",
    "printer_relay_proxy_port": "printer_relay_port",
    "printer_relay_proxy_queue_name": "printer_relay_queue_name",
    "printer_relay_proxy_mode_version": "printer_relay_mode_version",
    "printer_takeout_banner_enabled": "printer_packaging_banner_enabled",
    "printer_takeout_banner_lines": "printer_packaging_banner_lines",
    "printer_kitchen_title_takeout": "printer_kitchen_title_packaging",
}


def rename_key(key):
    key = str(key)
    if key in EXPLICIT_RENAMES:
        return EXPLICIT_RENAMES[key]
    if key.startswith("takeout_"):
        return "printer_relay_" + key[len("takeout_"):]
    return key


def config_files(data_dir):
    paths = []
    for name in ("settings.json", "settings.json.template"):
        path = os.path.join(data_dir, name)
        if os.path.isfile(path):
            paths.append(path)
    settings_dir = os.path.join(data_dir, "settings")
    if os.path.isdir(settings_dir):
        paths.extend(
            os.path.join(settings_dir, name)
            for name in sorted(os.listdir(settings_dir))
            if name.lower().endswith(".json")
            and os.path.isfile(os.path.join(settings_dir, name))
        )
    return paths


def rename_runtime_artifacts(data_dir, dry_run=False):
    """Rename relay runtime files/directories without touching SQLite."""
    pairs = (
        ("takeout_proxy_status.json", "printer_relay_status.json"),
        ("takeout_proxy_control.json", "printer_relay_control.json"),
        ("takeout_jobs.json", "printer_relay_jobs.json"),
        ("takeout_capture", "printer_relay_capture"),
    )
    changed = 0
    for old_name, new_name in pairs:
        old_path = os.path.join(data_dir, old_name)
        new_path = os.path.join(data_dir, new_name)
        if not os.path.exists(old_path):
            continue
        if dry_run:
            print("[预览] 将重命名：%s -> %s" % (old_path, new_path))
            changed += 1
            continue
        if os.path.exists(new_path):
            # Keep the canonical destination and remove only the old empty
            # control/status file; capture files are merged below.
            if os.path.isdir(old_path) and os.path.isdir(new_path):
                for name in os.listdir(old_path):
                    source = os.path.join(old_path, name)
                    target = os.path.join(new_path, name)
                    if not os.path.exists(target):
                        shutil.move(source, target)
                try:
                    os.rmdir(old_path)
                except OSError:
                    pass
            continue
        os.replace(old_path, new_path)
        changed += 1
    capture_dir = os.path.join(data_dir, "printer_relay_capture")
    if os.path.isdir(capture_dir) and not dry_run:
        for name in os.listdir(capture_dir):
            if name.startswith("takeout_"):
                os.replace(
                    os.path.join(capture_dir, name),
                    os.path.join(capture_dir, "printer_relay_" + name[len("takeout_"):]),
                )
    return changed


def migrate_file(path, backup_dir, dry_run=False):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, ValueError) as exc:
        return False, "读取失败：%s" % exc
    if not isinstance(value, dict):
        return False, "根节点不是对象"

    changed = {}
    # Canonical keys win if a file contains both generations.
    for key, item in value.items():
        new_key = rename_key(key)
        if new_key != key:
            changed[key] = new_key
    if not changed:
        return False, "无需迁移"

    migrated = {}
    for key, item in value.items():
        new_key = rename_key(key)
        if new_key in migrated and key != new_key:
            continue
        migrated[new_key] = item
    if dry_run:
        return True, "将迁移 %d 个字段" % len(changed)

    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, os.path.basename(path))
    shutil.copy2(path, backup_path)
    fd, temporary = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))
    os.close(fd)
    try:
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(migrated, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return True, "已迁移 %d 个字段，备份：%s" % (len(changed), backup_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="迁移 data 中旧 takeout 配置字段")
    parser.add_argument("--data", default=None, help="data 目录；默认使用项目根目录下的 data")
    parser.add_argument("--dry-run", action="store_true", help="只检查，不写入文件")
    args = parser.parse_args(argv)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.abspath(args.data or os.path.join(project_root, "data"))
    if not os.path.isdir(data_dir):
        parser.error("data 目录不存在：%s" % data_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(data_dir, "backups", "printer_relay_key_migration_" + stamp)
    total = 0
    legacy_module = os.path.join(data_dir, "settings", "takeout.json")
    canonical_module = os.path.join(data_dir, "settings", "printer_relay.json")
    if os.path.exists(legacy_module):
        if args.dry_run:
            action = u"合并后删除旧文件" if os.path.exists(canonical_module) else u"重命名"
            print("[预览] 将%s：%s -> %s" % (action, legacy_module, canonical_module))
            total += 1
        elif not os.path.exists(canonical_module):
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(legacy_module, os.path.join(backup_dir, "printer_relay_legacy.json"))
            os.replace(legacy_module, canonical_module)
            print("[迁移] 已重命名配置模块：%s -> %s" % (legacy_module, canonical_module))
            total += 1
        else:
            # Both generations exist: preserve canonical values, fill only
            # missing keys from the old file, then remove the old module.
            try:
                with open(legacy_module, "r", encoding="utf-8") as stream:
                    legacy_value = json.load(stream)
                with open(canonical_module, "r", encoding="utf-8") as stream:
                    canonical_value = json.load(stream)
                if not isinstance(legacy_value, dict) or not isinstance(canonical_value, dict):
                    raise ValueError("配置模块根节点必须是对象")
                old_migrated = {rename_key(key): item for key, item in legacy_value.items()}
                merged = dict(old_migrated)
                merged.update(canonical_value)
                os.makedirs(backup_dir, exist_ok=True)
                shutil.copy2(legacy_module, os.path.join(backup_dir, "printer_relay_legacy.json"))
                shutil.copy2(canonical_module, os.path.join(backup_dir, "printer_relay.json"))
                fd, temporary = tempfile.mkstemp(
                    prefix="printer_relay.json.", suffix=".tmp", dir=os.path.dirname(canonical_module)
                )
                os.close(fd)
                try:
                    with open(temporary, "w", encoding="utf-8") as stream:
                        json.dump(merged, stream, ensure_ascii=False, indent=2)
                        stream.write("\n")
                    os.replace(temporary, canonical_module)
                finally:
                    if os.path.exists(temporary):
                        os.remove(temporary)
                os.remove(legacy_module)
                print("[迁移] 已合并并删除旧配置模块：%s" % legacy_module)
                total += 1
            except (OSError, ValueError) as exc:
                print("[迁移 Warning] 无法合并旧配置模块：%s" % exc)
    total += rename_runtime_artifacts(data_dir, dry_run=args.dry_run)
    for path in config_files(data_dir):
        changed, message = migrate_file(path, backup_dir, dry_run=args.dry_run)
        if changed:
            total += 1
            print("[迁移] %s：%s" % (path, message))
    if total == 0:
        print("没有发现需要迁移的 takeout 配置字段。")
    elif args.dry_run:
        print("预览完成：%d 个文件将被更新。" % total)
    else:
        print("迁移完成：%d 个文件已更新。备份目录：%s" % (total, backup_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
