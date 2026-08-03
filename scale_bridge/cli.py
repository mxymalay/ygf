"""Technician commands for ScaleBridge; no command runs on ordinary POS start."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from typing import Optional

from .com0com import check_pair, list_pairs
from .configuration import load_config
from .ipc import read_status
from .lifecycle import (
    ScaleBridgeLifecycle,
    ScaleBridgeServiceController,
    application_root,
    collect_diagnostics,
    test_physical_scale,
    test_scale_channel,
    test_virtual_pair,
    write_diagnostic_report,
)


def _config_path(args) -> str:
    return args.config


def command_status(_args) -> int:
    print(json.dumps(read_status(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_check_pairs(args) -> int:
    config = load_config(_config_path(args))
    config.validate()
    pairs = list_pairs(args.setupc)
    checks = [
        check_pair(config.official_pos_virtual_port, config.official_bridge_port, pairs),
        check_pair(config.private_pos_virtual_port, config.private_bridge_port, pairs),
    ]
    if config.payment_pos_port:
        checks.append(check_pair(config.payment_pos_port, config.payment_plugin_port, pairs))
    for item in checks:
        print("%s <-> %s: %s%s" % (
            item.client_port,
            item.bridge_port,
            "OK" if item.present else "MISSING",
            " (pair %s)" % item.pair.index if item.pair else "",
        ))
    return 0 if all(item.present for item in checks) else 2


def command_probe(args) -> int:
    """Send the confirmed `$` query through a selected virtual endpoint.

    The chosen port must be unused while this maintenance test is running.
    This command never opens the physical scale port directly.
    """
    config = load_config(_config_path(args))
    port = args.port.upper() if args.port else config.private_pos_virtual_port
    result = test_scale_channel(config, port, timeout_seconds=args.timeout_ms / 1000.0)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.ok else 3


def command_test_physical(args) -> int:
    config = load_config(_config_path(args))
    result = test_physical_scale(config)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.ok else 3


def command_test_pair(args) -> int:
    result = test_virtual_pair(args.side_a, args.side_b)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.ok else 3


def command_diagnose(args) -> int:
    config = load_config(_config_path(args))
    report = collect_diagnostics(config)
    output = args.output or os.path.join(application_root(), "data", "scale_bridge_diagnosis.json")
    write_diagnostic_report(output, report)
    print(output)
    return 0


def command_service(args) -> int:
    controller = ScaleBridgeServiceController()
    if args.action == "query":
        result = asdict(controller.query())
    elif args.action == "start":
        result = {"changed": controller.start(), "state": asdict(controller.query())}
    else:
        result = {"changed": controller.stop(), "state": asdict(controller.query())}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_initialize(args) -> int:
    if not args.yes:
        raise RuntimeError("初始化会安装驱动/服务并创建端口；确认后必须显式添加 --yes")
    config = load_config(_config_path(args))
    report = ScaleBridgeLifecycle(_config_path(args)).initialize(config)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_remove(args) -> int:
    if not args.yes:
        raise RuntimeError("删除会移除本产品服务、配对和桥接配置；确认后必须显式添加 --yes")
    report = ScaleBridgeLifecycle(_config_path(args)).remove(remove_driver=args.remove_driver)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YGF ScaleBridge maintenance commands")
    parser.add_argument(
        "--config",
        default=os.path.join(application_root(), "data", "scale_bridge.json"),
        help="ScaleBridge JSON configuration",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="read service status only").set_defaults(handler=command_status)
    check = subparsers.add_parser("check-pairs", help="read and validate com0com pairs")
    check.add_argument("--setupc", help="explicit setupc.exe path if it is not in its normal location")
    check.set_defaults(handler=command_check_pairs)
    probe = subparsers.add_parser("probe", help="send one $ query through an unused virtual port")
    probe.add_argument("--port", help="virtual POS endpoint; defaults to PrivatePosVirtualPort")
    probe.add_argument("--timeout-ms", type=int, default=1500)
    probe.set_defaults(handler=command_probe)
    physical = subparsers.add_parser("test-physical", help="directly test selected physical scale while service is stopped")
    physical.set_defaults(handler=command_test_physical)
    pair = subparsers.add_parser("test-pair", help="test transparent communication in both directions")
    pair.add_argument("side_a")
    pair.add_argument("side_b")
    pair.set_defaults(handler=command_test_pair)
    diagnose = subparsers.add_parser("diagnose", help="write a complete read-only diagnostic report")
    diagnose.add_argument("--output")
    diagnose.set_defaults(handler=command_diagnose)
    service = subparsers.add_parser("service", help="query/start/stop the Windows service")
    service.add_argument("action", choices=("query", "start", "stop"))
    service.set_defaults(handler=command_service)
    initialize = subparsers.add_parser("initialize", help="perform idempotent first-run installation/repair")
    initialize.add_argument("--yes", action="store_true", help="confirm driver/service/port mutations")
    initialize.set_defaults(handler=command_initialize)
    remove = subparsers.add_parser("remove", help="remove only product-owned bridge resources")
    remove.add_argument("--yes", action="store_true", help="confirm removal")
    remove.add_argument("--remove-driver", action="store_true", help="also remove product-owned com0com if unused")
    remove.set_defaults(handler=command_remove)
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except Exception as exc:
        print("ERROR:", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
