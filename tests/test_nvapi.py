import threading
import unittest

from gpu_aux.adl import ADL_CONNECTOR_DISPLAY_PORT, Adapter, Port
from gpu_aux.nvapi import NvidiaAux


def _mock_port() -> Port:
    adapter = Adapter(
        index=0,
        name="Mock NVIDIA GPU",
        display_name="Mock NVIDIA GPU",
        bus=1,
        device=0,
        function=0,
        backend="NVIDIA",
    )
    return Port(
        adapter=adapter,
        index=0,
        logical_display_index=0x1234,
        physical_display_index=0,
        name="Mock DP",
        manufacturer="",
        display_type=0,
        output_type=ADL_CONNECTOR_DISPLAY_PORT,
        connector=ADL_CONNECTOR_DISPLAY_PORT,
        connected=True,
        backend="nvapi",
    )


class NvidiaAuxI2cWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        aux = NvidiaAux.__new__(NvidiaAux)
        aux._lock = threading.RLock()
        aux._closed = False
        self.calls = []

        def fake_aux(port, command, address, data, length_field):
            self.calls.append((command, address, bytes(data), length_field))
            return bytes(range(16))

        aux._aux = fake_aux
        self.aux = aux
        self.port = _mock_port()

    def test_read_dpcd_uses_n_minus_one_length_field(self) -> None:
        self.assertEqual(self.aux.read_dpcd(self.port, 0x100, 1), b"\x00")
        self.assertEqual(self.aux.read_dpcd(self.port, 0x100, 16), bytes(range(16)))

        self.assertEqual(self.calls[0], (1, 0x100, b"", 0))
        self.assertEqual(self.calls[1], (1, 0x100, b"", 15))

    def test_write_dpcd_uses_n_minus_one_length_field(self) -> None:
        self.aux.write_dpcd(self.port, 0x100, b"\x05")
        self.aux.write_dpcd(self.port, 0x100, bytes(range(16)))

        self.assertEqual(self.calls[0], (0, 0x100, b"\x05", 0))
        self.assertEqual(self.calls[1], (0, 0x100, bytes(range(16)), 15))

    def test_i2c_read_uses_n_minus_one_length_field(self) -> None:
        self.assertEqual(self.aux.i2c_read(self.port, 0x8E, 1), b"\x00")
        self.assertEqual(self.aux.i2c_read(self.port, 0x8E, 16), bytes(range(16)))

        self.assertEqual(self.calls[0], (3, 0x8E, b"", 0))
        self.assertEqual(self.calls[1], (3, 0x8E, b"", 15))

    def test_i2c_write_uses_n_minus_one_length_field(self) -> None:
        self.aux.i2c_write(self.port, 0x8E, b"\x05")
        self.aux.i2c_write(self.port, 0x8E, b"\x05\xAA")

        self.assertEqual(self.calls[0], (2, 0x8E, b"\x05", 0))
        self.assertEqual(self.calls[1], (2, 0x8E, b"\x05\xAA", 1))


if __name__ == "__main__":
    unittest.main()
