import unittest

from scale_bridge.arbiter import BridgeMode, OfficialPriorityArbiter
from scale_bridge.configuration import ScaleBridgeConfig, ScaleDeviceIdentity
from scale_bridge.device_discovery import SerialPortCandidate, resolve_saved_device
from scale_bridge.protocol import DibalFrameAssembler, parse_dibal_weight
from scale_bridge.bridge import BoundedPriorityQueue
from scale_bridge.bridge import ScaleBridgeRuntime
from scale_bridge.com0com import check_pair, parse_setupc_list


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


class Com0ComTests(unittest.TestCase):
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


class _FakeSerial(object):
    def __init__(self, port):
        self.port = port
        self.closed = False
        self.dtr = False
        self.rts = True

    def close(self):
        self.closed = True


class RuntimeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
