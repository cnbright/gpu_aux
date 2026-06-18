import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from amd_aux import AmdAux, AuxError


def test_port(aux: AmdAux, port) -> None:
    print(f"\n[{port.identity}] {port.name}")
    original = None
    try:
        head = aux.read_dpcd(port, 0x00000, 16)
        print(f"DPCD[0x00000:16] = {head.hex(' ').upper()}")

        original = aux.read_dpcd(port, 0x00102, 1)
        print(f"DPCD[0x00102] before = {original.hex().upper()}")
        aux.write_dpcd(port, 0x00102, b"\xC0")
        print(f"DPCD[0x00102] after  = {aux.read_dpcd(port, 0x00102, 1).hex().upper()}")

        aux.i2c_write(port, 0x30, 0, b"\x00")
        edid = aux.i2c_read(port, 0x50, 0, 128)
        print(f"EDID header_ok={edid[:8] == bytes.fromhex('00 FF FF FF FF FF FF 00')}, checksum_ok={sum(edid) % 256 == 0}")
        print(f"EDID={edid.hex(' ').upper()}")
    except AuxError as error:
        print(f"AUX operation failed: {error}")
    finally:
        if original is not None:
            aux.write_dpcd(port, 0x00102, original)
            print(f"DPCD[0x00102] restored = {aux.read_dpcd(port, 0x00102, 1).hex().upper()}")


def main() -> int:
    with AmdAux() as aux:
        for adapter in aux.adapters():
            for port in aux.ports(adapter):
                test_port(aux, port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
