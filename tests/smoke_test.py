import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from amd_aux import AmdAux, AuxError


def main() -> int:
    with AmdAux() as aux:
        adapters = aux.adapters()
        print(f"AMD adapters: {len(adapters)}")
        for adapter in adapters:
            print(f"GPU {adapter.index}: {adapter.name} ({adapter.display_name})")
            try:
                ports = aux.ports(adapter)
            except AuxError as error:
                print(f"  ports: {error}")
                continue
            for port in ports:
                print(
                    f"  {port.identity} ({port.kind}): {port.name!r}, manufacturer={port.manufacturer!r}, "
                    f"type={port.display_type}, output={port.output_type}, connector={port.connector}"
                )
                try:
                    data = aux.read_dpcd(port, 0x00000, 16)
                    print(f"    DPCD[0x00000:16] = {data.hex(' ').upper()}")
                except AuxError as error:
                    print(f"    DPCD read failed: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
