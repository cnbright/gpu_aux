import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from amd_aux import AuxError, AuxPort, enumerate_gpus_and_ports


def main() -> int:
    inventory = enumerate_gpus_and_ports()
    print(f"AMD GPUs: {len(inventory)}")

    for gpu in inventory:
        adapter = gpu.adapter
        print(f"GPU {gpu.gpu_index}: {adapter.name} ({adapter.display_name})")
        kind_indexes = defaultdict(int)
        for info in gpu.ports:
            kind_index = kind_indexes[info.kind]
            kind_indexes[info.kind] += 1
            print(
                f"  {info.identity} ({info.kind}[{kind_index}]): {info.name!r}, "
                f"manufacturer={info.manufacturer!r}, type={info.display_type}, "
                f"output={info.output_type}, connector={info.connector}"
            )
            try:
                with AuxPort(info.kind, kind_index, gpu.gpu_index) as port:
                    data = port.read_dpcd(0x00000, 16)
                print(f"    DPCD[0x00000:16] = {data.hex(' ').upper()}")
            except AuxError as error:
                print(f"    DPCD read failed: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
