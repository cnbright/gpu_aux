import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gpu_aux import AuxError, AuxPort, enumerate_gpus_and_ports


BACKEND = "INTEL"


def test_port(port: AuxPort) -> None:
    print(f"\n[{port.identity}] {port.info.name}")
    original = None
    try:
        head = port.read_dpcd(0x00000, 16)
        print(f"DPCD[0x00000:16] = {head.hex(' ').upper()}")

        original = port.read_dpcd(0x00102, 1)
        print(f"DPCD[0x00102] before = {original.hex().upper()}")
        port.write_dpcd(0x00102, b"\xC0")
        print(f"DPCD[0x00102] after  = {port.read_dpcd(0x00102, 1).hex().upper()}")

        port.i2c_write(0x60, b"\x00")
        port.i2c_write(0xA0, b"\x00")
        edid = port.i2c_read(0xA0, 128)
        header = bytes.fromhex("00 FF FF FF FF FF FF 00")
        print(f"EDID header_ok={edid[:8] == header}, checksum_ok={sum(edid) % 256 == 0}")
        print(f"EDID={edid.hex(' ').upper()}")
    except AuxError as error:
        print(f"AUX operation failed: {error}")
    finally:
        if original is not None:
            port.write_dpcd(0x00102, original)
            restored = port.read_dpcd(0x00102, 1)
            print(f"DPCD[0x00102] restored = {restored.hex().upper()}")


def main() -> int:
    for gpu in enumerate_gpus_and_ports(BACKEND):
        kind_indexes = defaultdict(int)
        for info in gpu.ports:
            kind_index = kind_indexes[info.kind]
            kind_indexes[info.kind] += 1
            with AuxPort(info.kind, kind_index, gpu.gpu_index, backend=BACKEND) as port:
                test_port(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
