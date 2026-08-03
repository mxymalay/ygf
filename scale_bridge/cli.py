"""Technician commands for ScaleBridge; no command runs on ordinary POS start."""
from __future__ import annotations

import argparse
import json
import time
from typing import Optional

from .com0com import check_pair, list_pairs
from .configuration import load_config
from .ipc import read_status


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
        check_pair(config.payment_pos_port, config.payment_plugin_port, pairs),
    ]
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
    import serial

    config = load_config(_config_path(args))
    port = args.port.upper() if args.port else config.private_pos_virtual_port
    if port == config.physical_scale_port.upper():
        raise ValueError("probe refuses to open the physical scale port; use a virtual POS endpoint")
    with serial.Serial(
        port=port,
        baudrate=config.baudrate,
        bytesize=config.data_bits,
        parity=config.parity,
        stopbits=config.stop_bits,
        timeout=0.1,
        write_timeout=0.5,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    ) as ser:
        ser.dtr = config.dtr_enable
        ser.rts = config.rts_enable
        ser.write(b"$")
        ser.flush()
        deadline = time.monotonic() + (args.timeout_ms / 1000.0)
        received = bytearray()
        while time.monotonic() < deadline:
            chunk = ser.read(getattr(ser, "in_waiting", 0) or 1)
            if chunk:
                received.extend(chunk)
                if b"\r" in received or b"\n" in received:
                    print("reply hex:", bytes(received).hex(" "))
                    print("reply text:", bytes(received).decode("ascii", errors="replace").strip())
                    return 0
        print("no scale reply within %d ms" % args.timeout_ms)
        return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YGF ScaleBridge maintenance commands")
    parser.add_argument("--config", default="data/scale_bridge.json", help="ScaleBridge JSON configuration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="read service status only").set_defaults(handler=command_status)
    check = subparsers.add_parser("check-pairs", help="read and validate com0com pairs")
    check.add_argument("--setupc", help="explicit setupc.exe path if it is not in its normal location")
    check.set_defaults(handler=command_check_pairs)
    probe = subparsers.add_parser("probe", help="send one $ query through an unused virtual port")
    probe.add_argument("--port", help="virtual POS endpoint; defaults to PrivatePosVirtualPort")
    probe.add_argument("--timeout-ms", type=int, default=1500)
    probe.set_defaults(handler=command_probe)
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
