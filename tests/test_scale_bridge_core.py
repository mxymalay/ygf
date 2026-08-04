import unittest
import os
import runpy
import tempfile
import sys
from unittest.mock import patch

from scale_bridge.arbiter import BridgeMode, OfficialPriorityArbiter
from scale_bridge.configuration import ScaleBridgeConfig, ScaleDeviceIdentity
from scale_bridge.device_discovery import SerialPortCandidate, resolve_saved_device
from scale_bridge.protocol import DibalFrameAssembler, parse_dibal_weight
from scale_bridge.bridge import BoundedPriorityQueue
from scale_bridge.bridge import ScaleBridgeRuntime, SimulatedScaleSerial
from scale_bridge.com0com import check_pair, create_pair, parse_setupc_list, remove_pair, _run_setupc
from scale_bridge.lifecycle import (
    Com0ComProvisioner,
    COM0COM_INSTALLER_SHA256,
    OwnedPair,
    PaymentPairLifecycle,
    PhysicalScaleTestResult,
    ProvisionReport,
    ScaleBridgeLifecycle,
    ScaleBridgeServiceController,
    load_manifest,
    save_manifest,
    test_physical_scale,
    test_scale_channel,
    test_virtual_pair,
    uninstall_com0com_driver,
    install_com0com_driver,
)


class WindowsServiceImportTests(unittest.TestCase):
    def test_service_module_supports_pythonservice_loose_file_import(self):
        """pywin32 can load service.py without package context in source mode."""
        source_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "scale_bridge", "service.py")
        )
        namespace = runpy.run_path(source_file, run_name="pythonservice_loose_import_test")
        self.assertIn("ScaleBridgeWindowsService", namespace)

    def test_source_service_host_registers_a_file_based_entry_point(self):
        """Source installs must not require pythonservice to find our package."""
        import scale_bridge.service as service_module
        import win32serviceutil

        host_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "scale_bridge_service.py")
        )
        captured = []
        with patch.object(
            service_module.win32serviceutil,
            "HandleCommandLine",
            side_effect=lambda service_class: captured.append(service_class) or 0,
        ), patch.object(sys, "argv", [host_file, "--help"]):
            with self.assertRaises(SystemExit):
                runpy.run_path(host_file, run_name="__main__")

        self.assertEqual(len(captured), 1)
        class_string = win32serviceutil.GetServiceClassString(
            captured[0],
            argv=[host_file],
        )
        self.assertEqual(
            class_string,
            os.path.splitext(host_file)[0] + ".ScaleBridgeWindowsService",
        )


class Com0ComInstallerTests(unittest.TestCase):
    def test_installer_runs_with_package_directory_as_working_directory(self):
        """The bundled setup must resolve its relative com0com.inf file."""
        import scale_bridge.lifecycle as lifecycle

        with tempfile.TemporaryDirectory() as directory:
            installer = os.path.join(directory, "Setup_com0com.exe")
            with open(installer, "wb") as stream:
                stream.write(b"signed installer placeholder")
            calls = []

            class Result:
                returncode = 0

            def runner(command, **kwargs):
                calls.append((command, kwargs))
                return Result()

            with patch.object(lifecycle, "is_administrator", return_value=True), patch.object(
                lifecycle, "sha256_file", return_value=COM0COM_INSTALLER_SHA256
            ), patch.object(lifecycle, "find_com0com_installer", return_value=installer), patch.object(
                lifecycle, "find_setupc", return_value="C:\\Program Files\\com0com\\setupc.exe"
            ):
                setupc = install_com0com_driver(runner=runner)

            self.assertEqual(setupc, "C:\\Program Files\\com0com\\setupc.exe")
            self.assertEqual(calls[0][0], [installer])
            self.assertEqual(calls[0][1]["cwd"], directory)


class ProtocolTests(unittest.TestCase):
    def test_split_and_combined_frames(self):
        assembler = DibalFrameAssembler(32)
        self.assertEqual(assembler.feed(b"000.")[0], [])
        frames, discarded = assembler.feed(b"402\r000.500\r")
        self.assertEqual(frames, [b"000.402", b"000.500"])
        self.assertEqual(discarded, 0)
        self.assertEqual(parse_dibal_weight(frames[0]), 0.402)

    def test_oversize_unterminated_data_is_dropped(self):
        assembler = DibalFrameAssembler(16)
        frames, discarded = assembler.feed(b"x" * 17)
        self.assertEqual(frames, [])
        self.assertEqual(discarded, 17)


class ArbiterTests(unittest.TestCase):
    def test_startup_stays_unknown_until_first_pos_query(self):
        arbiter = OfficialPriorityArbiter()
        self.assertEqual(arbiter.status()["mode"], BridgeMode.UNKNOWN.value)
        arbiter.route_private(b"$")
        self.assertEqual(arbiter.status()["mode"], BridgeMode.PRIVATE_ACTIVE.value)

    def test_official_query_suppresses_private_query_but_broadcasts_reply(self):
        now = [10.0]
        arbiter = OfficialPriorityArbiter(clock=lambda: now[0])
        self.assertEqual(arbiter.route_official(b"$"), b"$")
        self.assertEqual(arbiter.mode, BridgeMode.OFFICIAL_ACTIVE)
        self.assertEqual(arbiter.route_private(b"$"), b"")
        self.assertEqual(arbiter.suppressed_private_queries, 1)
        self.assertEqual(arbiter.accept_scale_bytes(b"000.402\r"), [0.402])
        now[0] += 1.1
        self.assertEqual(arbiter.route_private(b"$"), b"$")
        self.assertEqual(arbiter.mode, BridgeMode.PRIVATE_ACTIVE)

    def test_official_write_queue_precedes_private_queue(self):
        queue = BoundedPriorityQueue(4)
        self.assertTrue(queue.put(b"private"))
        self.assertTrue(queue.put(b"official", high_priority=True))
        self.assertEqual(queue.get(), b"official")
        self.assertEqual(queue.get(), b"private")

    def test_bounded_queue_drops_new_data_when_full(self):
        queue = BoundedPriorityQueue(1)
        self.assertTrue(queue.put(b"first"))
        self.assertFalse(queue.put(b"second"))
        self.assertEqual(queue.dropped, 1)

    def test_official_command_evicts_private_backlog_when_queue_is_full(self):
        queue = BoundedPriorityQueue(1)
        self.assertTrue(queue.put(b"private"))
        self.assertTrue(queue.put(b"official", high_priority=True))
        self.assertEqual(queue.get(), b"official")
        self.assertEqual(queue.dropped, 1)


class ConfigurationTests(unittest.TestCase):
    def test_config_rejects_duplicate_ports(self):
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_bridge_port="CNCB1",
            private_bridge_port="CNCB2",
        )
        cfg.validate()
        cfg.private_pos_virtual_port = "COM2"
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_device_identity_requires_unique_match(self):
        saved = ScaleDeviceIdentity(vid="1A86", pid="7523")
        candidates = [
            SerialPortCandidate("COM5", "CH340 A", vid="1A86", pid="7523"),
            SerialPortCandidate("COM8", "CH340 B", vid="1A86", pid="7523"),
        ]
        resolved, ambiguous = resolve_saved_device(saved, candidates)
        self.assertIsNone(resolved)
        self.assertEqual([item.port for item in ambiguous], ["COM5", "COM8"])

    def test_string_boolean_values_are_parsed_correctly(self):
        cfg = ScaleBridgeConfig.from_dict({
            "PhysicalScalePort": "COM1",
            "OfficialBridgePort": "CNCB0",
            "PrivateBridgePort": "CNCB1",
            "DtrEnable": "false",
            "RtsEnable": "true",
        })
        self.assertFalse(cfg.dtr_enable)
        self.assertTrue(cfg.rts_enable)

    def test_payment_pair_is_configurable_or_can_be_unused(self):
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_bridge_port="CNCB0",
            private_bridge_port="CNCB1",
            payment_pos_port="",
            payment_plugin_port="",
        )
        cfg.validate()
        cfg.payment_pos_port = "COM12"
        cfg.payment_plugin_port = "COM13"
        cfg.validate()
        cfg.payment_plugin_port = ""
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_invalid_port_names_are_rejected_before_setupc(self):
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="NOT-A-COM"),
            official_bridge_port="CNCB0",
            private_bridge_port="CNCB1",
        )
        with self.assertRaisesRegex(ValueError, "COM port name"):
            cfg.validate()


class Com0ComTests(unittest.TestCase):
    def test_setupc_uses_its_installation_directory_for_inf_files(self):
        calls = []

        class Result(object):
            returncode = 0
            stdout = b""
            stderr = b""

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return Result()

        with tempfile.TemporaryDirectory() as directory:
            setup_dir = os.path.join(directory, "com0com")
            os.makedirs(setup_dir)
            executable = os.path.join(setup_dir, "setupc.exe")
            _run_setupc(executable, ["list"], 10, runner)
            self.assertEqual(calls[0][1]["cwd"], setup_dir)

    def test_parse_and_check_named_pair(self):
        pairs = parse_setupc_list(
            "CNCA0 PortName=COM2,EmuBR=yes\r\n"
            "CNCB0 PortName=CNCB0\r\n"
            "CNCA1 PortName=COM3\r\n"
            "CNCB1 PortName=CNCB1\r\n"
        )
        self.assertEqual(pairs[0].side_a, "COM2")
        self.assertTrue(check_pair("COM2", "CNCB0", pairs).present)
        self.assertFalse(check_pair("COM2", "CNCB1", pairs).present)

    def test_create_named_pair_and_remove_use_exact_setupc_commands(self):
        calls = []

        class Result(object):
            returncode = 0
            stdout = b""
            stderr = b""

        def runner(command, **_kwargs):
            calls.append(command)
            return Result()

        create_pair("COM10", "COM11", 3, "setupc.exe", True, runner)
        remove_pair(3, "setupc.exe", True, runner)
        self.assertEqual(
            calls[0],
            ["setupc.exe", "install", "3", "PortName=COM10,EmuBR=yes", "PortName=COM11,EmuBR=yes"],
        )
        self.assertEqual(calls[1], ["setupc.exe", "remove", "3"])


class _StatefulSetupCRunner(object):
    def __init__(self):
        self.pairs = {}
        self.commands = []

    class Result(object):
        def __init__(self, output=b"", returncode=0):
            self.returncode = returncode
            self.stdout = output
            self.stderr = b""

    def _list_output(self):
        lines = []
        for index, (side_a, side_b) in sorted(self.pairs.items()):
            lines.append("CNCA%d PortName=%s" % (index, side_a))
            lines.append("CNCB%d PortName=%s" % (index, side_b))
        return ("\r\n".join(lines) + ("\r\n" if lines else "")).encode("ascii")

    def __call__(self, command, **_kwargs):
        self.commands.append(command)
        action = command[1]
        if action == "list":
            return self.Result(self._list_output())
        if action == "install":
            index = int(command[2])
            side_a = command[3].split("=", 1)[1].split(",", 1)[0]
            side_b = "CNCB%d" % index if command[4] == "-" else command[4].split("=", 1)[1].split(",", 1)[0]
            self.pairs[index] = (side_a, side_b)
            return self.Result()
        if action == "remove":
            self.pairs.pop(int(command[2]), None)
            return self.Result()
        return self.Result(returncode=1)


class ProvisioningTests(unittest.TestCase):
    def test_default_provisioning_scope_excludes_payment_pair(self):
        runner = _StatefulSetupCRunner()
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_bridge_port="",
            private_bridge_port="",
            payment_pos_port="COM10",
            payment_plugin_port="COM11",
        )
        with tempfile.TemporaryDirectory() as directory:
            provisioner = Com0ComProvisioner(
                "setupc.exe",
                os.path.join(directory, "installation.json"),
                runner=runner,
                port_enumerator=lambda include_virtual=True: [],
            )
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
                report = provisioner.ensure_required_pairs(cfg)
        self.assertEqual(len(report.created), 2)
        self.assertFalse(any("COM10" in pair for pair in runner.pairs.values()))

    def test_full_provision_is_idempotent_and_records_exact_owned_pairs(self):
        runner = _StatefulSetupCRunner()
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_bridge_port="",
            private_bridge_port="",
            payment_pos_port="COM10",
            payment_plugin_port="COM11",
        )
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = os.path.join(directory, "installation.json")
            provisioner = Com0ComProvisioner(
                "setupc.exe",
                manifest_path,
                runner=runner,
                port_enumerator=lambda include_virtual=True: [],
            )
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
                report = provisioner.ensure_required_pairs(cfg, include_payment=True)
                install_count = len([item for item in runner.commands if item[1] == "install"])
                second = provisioner.ensure_required_pairs(cfg, include_payment=True)
            self.assertEqual(len(report.created), 3)
            self.assertEqual(second.created, [])
            self.assertEqual(install_count, 3)
            self.assertEqual(len([item for item in runner.commands if item[1] == "install"]), 3)
            self.assertEqual(cfg.payment_plugin_port, "COM11")
            self.assertEqual(cfg.official_bridge_port, "CNCB1")
            self.assertEqual(cfg.private_bridge_port, "CNCB2")
            manifest = load_manifest(manifest_path)
            self.assertEqual({item.index for item in manifest.created_pairs}, {0, 1, 2})

            with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
                removed, skipped = provisioner.remove_owned_pairs()
            self.assertEqual(len(removed), 3)
            self.assertEqual(skipped, [])
            self.assertEqual(runner.pairs, {})

    def test_repair_replaces_changed_owned_pair_and_removes_obsolete_pair(self):
        runner = _StatefulSetupCRunner()
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_bridge_port="",
            private_bridge_port="",
            payment_pos_port="COM10",
            payment_plugin_port="COM11",
        )
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = os.path.join(directory, "installation.json")
            provisioner = Com0ComProvisioner(
                "setupc.exe",
                manifest_path,
                runner=runner,
                port_enumerator=lambda include_virtual=True: [],
            )
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
                provisioner.ensure_required_pairs(cfg, include_payment=True)
                old_official_index = next(
                    index for index, pair in runner.pairs.items() if "COM2" in pair
                )
                cfg.official_pos_virtual_port = "COM4"
                cfg.official_bridge_port = ""
                report = provisioner.ensure_required_pairs(cfg, include_payment=True)

            self.assertTrue(any("COM2" in item for item in report.removed_obsolete))
            self.assertNotIn(old_official_index, runner.pairs)
            self.assertTrue(any("COM4" in pair for pair in runner.pairs.values()))
            manifest = load_manifest(manifest_path)
            self.assertFalse(any(item.index == old_official_index for item in manifest.created_pairs))

    def test_scale_only_repair_does_not_remove_owned_payment_pair(self):
        runner = _StatefulSetupCRunner()
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_bridge_port="",
            private_bridge_port="",
            payment_pos_port="COM10",
            payment_plugin_port="COM11",
        )
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = os.path.join(directory, "installation.json")
            provisioner = Com0ComProvisioner(
                "setupc.exe",
                manifest_path,
                runner=runner,
                port_enumerator=lambda include_virtual=True: [],
            )
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
                provisioner.ensure_required_pairs(cfg, include_payment=True)
                payment_index = next(
                    index for index, pair in runner.pairs.items() if "COM10" in pair
                )
                report = provisioner.ensure_required_pairs(
                    cfg, include_scale=True, include_payment=False
                )

            self.assertFalse(any("COM10" in item for item in report.removed_obsolete))
            self.assertIn(payment_index, runner.pairs)
            self.assertEqual(len(runner.pairs), 3)

    def test_payment_lifecycle_creates_and_removes_only_payment_pair(self):
        runner = _StatefulSetupCRunner()
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = os.path.join(directory, "installation.json")
            provisioner = Com0ComProvisioner(
                "setupc.exe",
                manifest_path,
                runner=runner,
                port_enumerator=lambda include_virtual=True: [],
            )
            lifecycle = PaymentPairLifecycle(manifest_path, provisioner)
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True), patch(
                "scale_bridge.lifecycle.find_setupc", return_value="setupc.exe"
            ):
                report = lifecycle.initialize("COM10", "COM11")
                removed, skipped = lifecycle.remove()
            self.assertEqual(len(report.created), 1)
            self.assertEqual(len(removed), 1)
            self.assertEqual(skipped, [])
            self.assertEqual(runner.pairs, {})

    def test_real_port_conflict_is_not_overwritten(self):
        runner = _StatefulSetupCRunner()
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_pos_virtual_port="COM2",
            official_bridge_port="",
            private_bridge_port="",
            payment_pos_port="",
            payment_plugin_port="",
        )
        occupied = SerialPortCandidate("COM2", "Real UART", is_virtual=False)
        with tempfile.TemporaryDirectory() as directory:
            provisioner = Com0ComProvisioner(
                "setupc.exe",
                os.path.join(directory, "installation.json"),
                runner=runner,
                port_enumerator=lambda include_virtual=True: [occupied],
            )
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "不会覆盖"):
                    provisioner.ensure_required_pairs(
                        cfg, include_scale=True, include_payment=False
                    )
        self.assertFalse(any(item[1] == "install" for item in runner.commands))

    def test_existing_peer_cannot_be_reused_in_a_second_pair(self):
        runner = _StatefulSetupCRunner()
        runner.pairs[0] = ("COM10", "COM11")
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_pos_virtual_port="COM2",
            official_bridge_port="COM11",
            private_bridge_port="",
            payment_pos_port="",
            payment_plugin_port="",
        )
        with tempfile.TemporaryDirectory() as directory:
            provisioner = Com0ComProvisioner(
                "setupc.exe",
                os.path.join(directory, "installation.json"),
                runner=runner,
                port_enumerator=lambda include_virtual=True: [],
            )
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "不能重复用于新配对"):
                    provisioner.ensure_required_pairs(
                        cfg, include_scale=True, include_payment=False
                    )
        self.assertFalse(any(item[1] == "install" for item in runner.commands))

    def test_delete_preflight_blocks_all_removal_if_one_owned_pair_changed(self):
        runner = _StatefulSetupCRunner()
        runner.pairs = {0: ("COM2", "CNCB0"), 1: ("COM3", "OTHER")}
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = os.path.join(directory, "installation.json")
            manifest = load_manifest(manifest_path)
            manifest.created_pairs = [
                OwnedPair("official_scale", 0, "COM2", "CNCB0"),
                OwnedPair("private_scale", 1, "COM3", "CNCB1"),
            ]
            save_manifest(manifest, manifest_path)
            provisioner = Com0ComProvisioner(
                "setupc.exe",
                manifest_path,
                runner=runner,
                port_enumerator=lambda include_virtual=True: [],
            )
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
                removed, skipped = provisioner.remove_owned_pairs()
        self.assertEqual(removed, [])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(runner.pairs, {0: ("COM2", "CNCB0"), 1: ("COM3", "OTHER")})
        self.assertFalse(any(item[1] == "remove" for item in runner.commands))

    def test_scale_pair_removal_preserves_owned_payment_pair(self):
        runner = _StatefulSetupCRunner()
        runner.pairs = {0: ("COM10", "COM11"), 1: ("COM2", "CNCB1")}
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = os.path.join(directory, "installation.json")
            manifest = load_manifest(manifest_path)
            manifest.created_pairs = [
                OwnedPair("payment", 0, "COM10", "COM11"),
                OwnedPair("official_scale", 1, "COM2", "CNCB1"),
            ]
            save_manifest(manifest, manifest_path)
            provisioner = Com0ComProvisioner(
                "setupc.exe",
                manifest_path,
                runner=runner,
                port_enumerator=lambda include_virtual=True: [],
            )
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
                removed, skipped = provisioner.remove_owned_pairs({"official_scale"})
            self.assertEqual(len(removed), 1)
            self.assertEqual(skipped, [])
            self.assertEqual(runner.pairs, {0: ("COM10", "COM11")})
            self.assertEqual(
                [item.purpose for item in load_manifest(manifest_path).created_pairs],
                ["payment"],
            )


class _ServiceRunner(object):
    def __init__(self):
        self.installed = False
        self.state = 0
        self.commands = []

    class Result(object):
        def __init__(self, output=b"", returncode=0):
            self.returncode = returncode
            self.stdout = output
            self.stderr = b""

    def __call__(self, command, **_kwargs):
        self.commands.append(command)
        if command[:2] == ["sc.exe", "query"]:
            if not self.installed:
                return self.Result(b"not installed", 1060)
            output = ("SERVICE_NAME: YgfScaleBridge\r\n        STATE              : %d  %s\r\n" % (
                self.state, {1: "STOPPED", 4: "RUNNING"}.get(self.state, "PENDING")
            )).encode("ascii")
            return self.Result(output)
        action = command[-1]
        if action == "install":
            self.installed, self.state = True, 1
        elif action == "start":
            self.state = 4
        elif action == "stop":
            self.state = 1
        elif action == "remove":
            self.installed, self.state = False, 0
        return self.Result()


class ServiceLifecycleTests(unittest.TestCase):
    def test_install_start_stop_remove(self):
        runner = _ServiceRunner()
        controller = ScaleBridgeServiceController(["ScaleBridgeService.exe"], runner)
        with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
            self.assertTrue(controller.install())
            self.assertTrue(controller.start())
            self.assertEqual(controller.query().state, "RUNNING")
            self.assertTrue(controller.stop())
            self.assertTrue(controller.remove())
        self.assertFalse(controller.query().installed)

    def test_frozen_service_without_arguments_enters_scm_dispatcher(self):
        from scale_bridge import service as service_module

        class Manager(object):
            def __init__(self):
                self.calls = []

            def Initialize(self):
                self.calls.append("initialize")

            def PrepareToHostSingle(self, service_class):
                self.calls.append(("prepare", service_class))

            def StartServiceCtrlDispatcher(self):
                self.calls.append("dispatch")

        manager = Manager()
        with patch.object(sys, "frozen", True, create=True), patch.object(
            service_module, "servicemanager", manager
        ):
            self.assertEqual(service_module.main([]), 0)
        self.assertEqual(manager.calls[0], "initialize")
        self.assertEqual(manager.calls[-1], "dispatch")

    def test_service_command_propagates_pywin32_failure_code(self):
        from scale_bridge import service as service_module
        with patch.object(service_module.win32serviceutil, "HandleCommandLine", return_value=5):
            self.assertEqual(service_module.main(["install"]), 5)


class _FakeSerial(object):
    def __init__(self, port):
        self.port = port
        self.closed = False
        self.dtr = False
        self.rts = True

    def close(self):
        self.closed = True


class RuntimeTests(unittest.TestCase):
    def test_simulated_scale_answers_dibal_query(self):
        serial = SimulatedScaleSerial(0.5)
        serial.write(b"$")
        self.assertEqual(serial.read(64), b"0.500\r")

    def test_partial_port_open_is_closed_and_queues_are_not_replayed(self):
        opened = []

        def factory(**kwargs):
            if kwargs["port"] == "CNCB0":
                raise OSError("official endpoint unavailable")
            item = _FakeSerial(kwargs["port"])
            opened.append(item)
            return item

        runtime = ScaleBridgeRuntime(
            ScaleBridgeConfig(
                physical_scale=ScaleDeviceIdentity(port="COM5"),
                official_bridge_port="CNCB0",
                private_bridge_port="CNCB1",
            ),
            serial_factory=factory,
        )
        runtime._physical_queue.put(b"stale")
        with self.assertRaises(OSError):
            runtime._open_session()
        self.assertEqual(len(runtime._physical_queue), 0)
        self.assertTrue(opened[0].closed)

    def test_physical_scale_query_handles_split_reply(self):
        class ScaleSerial(_FakeSerial):
            def __init__(self, **kwargs):
                super(ScaleSerial, self).__init__(kwargs["port"])
                self.chunks = [b"0", b"00.402\r"]
                self.writes = []

            @property
            def in_waiting(self):
                return len(self.chunks[0]) if self.chunks else 0

            def read(self, _size):
                return self.chunks.pop(0) if self.chunks else b""

            def write(self, data):
                self.writes.append(data)

            def flush(self):
                pass

        serial_instance = ScaleSerial(port="COM5")
        cfg = ScaleBridgeConfig(physical_scale=ScaleDeviceIdentity(port="COM5"))
        result = test_physical_scale(cfg, serial_factory=lambda **_kwargs: serial_instance)
        self.assertTrue(result.ok)
        self.assertEqual(result.weight_kg, 0.402)
        self.assertEqual(serial_instance.writes[0], b"$")

    def test_physical_scale_missing_device_returns_without_opening_port(self):
        cfg = ScaleBridgeConfig(physical_scale=ScaleDeviceIdentity(port="COM99"))
        with patch("scale_bridge.lifecycle.enumerate_serial_ports", return_value=[]):
            result = test_physical_scale(cfg)
        self.assertFalse(result.ok)
        self.assertIn("未出现在 Windows 真实串口设备列表", result.message)

    def test_virtual_pos_channel_queries_scale_end_to_end(self):
        class ChannelSerial(_FakeSerial):
            def __init__(self, **kwargs):
                super(ChannelSerial, self).__init__(kwargs["port"])
                self.chunks = [b"000.", b"625\r"]
                self.writes = []

            @property
            def in_waiting(self):
                return len(self.chunks[0]) if self.chunks else 0

            def read(self, _size):
                return self.chunks.pop(0) if self.chunks else b""

            def write(self, data):
                self.writes.append(data)

            def flush(self):
                pass

        serial_instance = ChannelSerial(port="COM3")
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_bridge_port="CNCB0",
            private_bridge_port="CNCB1",
        )
        result = test_scale_channel(
            cfg, "COM3", serial_factory=lambda **_kwargs: serial_instance
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.weight_kg, 0.625)
        self.assertEqual(serial_instance.writes[0], b"$")

    def test_virtual_pos_channel_refuses_non_pos_endpoint(self):
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_bridge_port="CNCB0",
            private_bridge_port="CNCB1",
        )
        result = test_scale_channel(cfg, "COM5", serial_factory=lambda **_kwargs: None)
        self.assertFalse(result.ok)
        self.assertIn("只能测试", result.message)

    def test_runtime_refuses_same_com_name_when_hardware_identity_changed(self):
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5", pnp_device_id="USB\\ORIGINAL"),
            official_bridge_port="CNCB0",
            private_bridge_port="CNCB1",
        )
        runtime = ScaleBridgeRuntime(cfg)
        replacement = SerialPortCandidate("COM5", "Other UART", pnp_device_id="USB\\OTHER")
        with patch("scale_bridge.bridge.enumerate_serial_ports", return_value=[replacement]):
            with self.assertRaisesRegex(RuntimeError, "different device"):
                runtime._prepare_physical_port()

    def test_runtime_rebinds_unique_saved_device_to_new_com_number(self):
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5", pnp_device_id="USB\\SCALE123"),
            official_bridge_port="CNCB0",
            private_bridge_port="CNCB1",
        )
        moved = SerialPortCandidate("COM8", "Scale UART", pnp_device_id="USB\\SCALE123")
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "bridge.json")
            runtime = ScaleBridgeRuntime(cfg, config_path=path)
            with patch("scale_bridge.bridge.enumerate_serial_ports", return_value=[moved]):
                runtime._prepare_physical_port()
            self.assertEqual(cfg.physical_scale_port, "COM8")
            self.assertEqual(runtime.status().rebound_count, 1)


class DriverRemovalTests(unittest.TestCase):
    def test_uninstall_uses_registered_exact_command_only_when_no_pairs_remain(self):
        calls = []

        class Result(object):
            returncode = 0
            stdout = b""
            stderr = b""

        def runner(command, **_kwargs):
            calls.append(command)
            return Result()

        with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
            removed = uninstall_com0com_driver(
                "setupc.exe", ["com0com-uninstall.exe", "/quiet"], runner
            )
        self.assertTrue(removed)
        self.assertEqual(calls[-1], ["com0com-uninstall.exe", "/quiet"])

    def test_uninstall_refuses_while_any_pair_remains(self):
        class Result(object):
            returncode = 0
            stdout = b"CNCA9 PortName=COM20\r\nCNCB9 PortName=COM21\r\n"
            stderr = b""

        with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "仍存在"):
                uninstall_com0com_driver(
                    "setupc.exe", ["com0com-uninstall.exe"], lambda *_args, **_kwargs: Result()
                )


class VirtualPairTests(unittest.TestCase):
    def test_bidirectional_transparent_pair(self):
        endpoints = {}

        class Endpoint(object):
            def __init__(self, port):
                self.port = port
                self.buffer = bytearray()
                self.dtr = False
                self.rts = False

            @property
            def in_waiting(self):
                return len(self.buffer)

            def write(self, data):
                other_port = "COM11" if self.port == "COM10" else "COM10"
                endpoints[other_port].buffer.extend(data)

            def read(self, size):
                data = bytes(self.buffer[:size])
                del self.buffer[:size]
                return data

            def flush(self):
                pass

            def close(self):
                pass

        def factory(**kwargs):
            endpoint = Endpoint(kwargs["port"])
            endpoints[kwargs["port"]] = endpoint
            return endpoint

        result = test_virtual_pair("COM10", "COM11", serial_factory=factory)
        self.assertTrue(result.ok)


class _FakeProvisioner(object):
    def ensure_required_pairs(self, config, **_kwargs):
        config.official_bridge_port = "CNCB4"
        config.private_bridge_port = "CNCB5"
        return ProvisionReport(created=["COM2 ↔ CNCB4", "COM3 ↔ CNCB5"])

    def remove_owned_pairs(self, _purposes=None):
        return ["COM2 ↔ CNCB4", "COM3 ↔ CNCB5"], []


class _FakeLifecycleService(object):
    def __init__(self):
        self.installed = False
        self.running = False

    def query(self):
        return type("State", (), {
            "installed": self.installed,
            "state_code": 4 if self.running else (1 if self.installed else 0),
        })()

    def install(self):
        changed = not self.installed
        self.installed = True
        return changed

    def start(self):
        changed = not self.running
        self.running = True
        return changed

    def stop(self):
        changed = self.running
        self.running = False
        return changed

    def remove(self):
        changed = self.installed
        self.installed = False
        self.running = False
        return changed


class FullLifecycleTests(unittest.TestCase):
    def test_virtual_only_initialization_skips_physical_scale_and_service(self):
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_bridge_port="",
            private_bridge_port="",
            payment_pos_port="",
            payment_plugin_port="",
        )
        with tempfile.TemporaryDirectory() as directory:
            lifecycle = ScaleBridgeLifecycle(
                os.path.join(directory, "scale_bridge.json"),
                os.path.join(directory, "installation.json"),
                provisioner=_FakeProvisioner(),
                service=_FakeLifecycleService(),
            )
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True), patch(
                "scale_bridge.lifecycle.find_setupc", return_value="setupc.exe"
            ):
                report = lifecycle.initialize_virtual_only(cfg)
            self.assertEqual(len(report.created), 2)
            self.assertEqual(cfg.physical_scale_port, "COM5")
            self.assertFalse(os.path.exists(os.path.join(directory, "scale_bridge.json")))

    def test_scale_initialize_rejects_pairs_missing_from_windows_device_list(self):
        runner = _StatefulSetupCRunner()
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_bridge_port="",
            private_bridge_port="",
            payment_pos_port="",
            payment_plugin_port="",
        )
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = os.path.join(directory, "installation.json")
            config_path = os.path.join(directory, "scale_bridge.json")
            provisioner = Com0ComProvisioner(
                "setupc.exe",
                manifest_path,
                runner=runner,
                port_enumerator=lambda include_virtual=True: [],
            )
            service = _FakeLifecycleService()
            lifecycle = ScaleBridgeLifecycle(
                config_path,
                manifest_path,
                provisioner=provisioner,
                service=service,
                verify_enumeration=True,
            )
            tester = lambda _cfg: PhysicalScaleTestResult(True, "COM5", 0.402, "30 30", "ok")
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True), patch(
                "scale_bridge.lifecycle.find_setupc", return_value="setupc.exe"
            ):
                with self.assertRaisesRegex(RuntimeError, "设备管理器未枚举"):
                    lifecycle.initialize(cfg, tester)
            self.assertFalse(os.path.exists(config_path))
            self.assertFalse(service.installed)

    def test_failed_physical_retest_restores_previously_running_service(self):
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_bridge_port="CNCB0",
            private_bridge_port="CNCB1",
            payment_pos_port="",
            payment_plugin_port="",
        )
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = os.path.join(directory, "installation.json")
            manifest = load_manifest(manifest_path)
            manifest.service_owned = True
            save_manifest(manifest, manifest_path)
            service = _FakeLifecycleService()
            service.installed = True
            service.running = True
            lifecycle = ScaleBridgeLifecycle(
                os.path.join(directory, "scale_bridge.json"),
                manifest_path,
                provisioner=_FakeProvisioner(),
                service=service,
            )
            tester = lambda _cfg: PhysicalScaleTestResult(
                False, "COM5", message="no reply"
            )
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "物理电子秤测试失败"):
                    lifecycle.initialize(cfg, tester)
            self.assertTrue(service.running)

    def test_initialize_and_remove_touch_only_bridge_files(self):
        cfg = ScaleBridgeConfig(
            physical_scale=ScaleDeviceIdentity(port="COM5"),
            official_bridge_port="",
            private_bridge_port="",
            payment_pos_port="",
            payment_plugin_port="",
        )
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, "scale_bridge.json")
            manifest_path = os.path.join(directory, "installation.json")
            unrelated_path = os.path.join(directory, "existing_pos_settings.json")
            with open(unrelated_path, "w", encoding="utf-8") as handle:
                handle.write("unchanged")
            service = _FakeLifecycleService()
            lifecycle = ScaleBridgeLifecycle(
                config_path,
                manifest_path,
                provisioner=_FakeProvisioner(),
                service=service,
            )
            tester = lambda _cfg: PhysicalScaleTestResult(True, "COM5", 0.402, "30 30", "ok")
            with patch("scale_bridge.lifecycle.is_administrator", return_value=True), patch(
                "scale_bridge.lifecycle.find_setupc", return_value="setupc.exe"
            ):
                report = lifecycle.initialize(cfg, tester)
                self.assertTrue(report.service_installed)
                self.assertTrue(os.path.isfile(config_path))
                removal = lifecycle.remove(remove_driver=True)
            self.assertTrue(removal.service_removed)
            self.assertIn("安全保留", removal.driver_retained_reason)
            self.assertFalse(os.path.exists(config_path))
            with open(unrelated_path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "unchanged")


if __name__ == "__main__":
    unittest.main()
