import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gpu_aux import AuxError, AuxPort, enumerate_gpus, enumerate_ports


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: smoke_test.py AMD|NVIDIA|INTEL")
        return 2
    backend = sys.argv[1]
    try:
        gpus = enumerate_gpus(backend)
    except AuxError as error:
        print(f"{backend.upper()} GPU enumeration failed: {error}")
        return 1
    print(f"{backend.upper()} GPUs: {len(gpus)}")

    for gpu_index, adapter in enumerate(gpus):
        print(f"GPU {gpu_index}: {adapter.backend} {adapter.name} ({adapter.display_name})")
        kind_indexes = defaultdict(int)
        for info in enumerate_ports(backend, gpu_index):
            kind_index = kind_indexes[info.kind]
            kind_indexes[info.kind] += 1
            print(
                f"  {info.identity} ({info.kind}[{kind_index}]): {info.name!r}, "
                f"manufacturer={info.manufacturer!r}, type={info.display_type}, "
                f"output={info.output_type}, connector={info.connector}"
            )
            try:
                with AuxPort(info.kind, kind_index, gpu_index, backend=backend) as port:
                    data = port.read_dpcd(0x00000, 16)
                print(f"    DPCD[0x00000:16] = {data.hex(' ').upper()}")
            except AuxError as error:
                print(f"    DPCD read failed: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
