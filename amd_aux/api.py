"""Object-oriented public API for selecting and using one AUX port."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from .adl import Adapter, AmdAux, AuxError, Port


_context_lock = threading.RLock()
_shared_aux = None
_context_users = 0


def _acquire_aux() -> AmdAux:
    global _shared_aux, _context_users
    with _context_lock:
        if _shared_aux is None:
            _shared_aux = AmdAux()
        _context_users += 1
        return _shared_aux


def _release_aux(aux: AmdAux) -> None:
    global _shared_aux, _context_users
    with _context_lock:
        if aux is not _shared_aux or _context_users <= 0:
            return
        _context_users -= 1
        if _context_users == 0:
            aux.close()
            _shared_aux = None


@dataclass(frozen=True)
class GpuPorts:
    """A physical GPU and a snapshot of its connected DP/eDP ports."""

    gpu_index: int
    adapter: Adapter
    ports: tuple[Port, ...]


def enumerate_gpus_and_ports() -> list[GpuPorts]:
    """Return all physical AMD GPUs and their connected DP/eDP ports."""

    aux = _acquire_aux()
    try:
        result = []
        for gpu_index, adapter in enumerate(aux.adapters()):
            result.append(
                GpuPorts(
                    gpu_index=gpu_index,
                    adapter=adapter,
                    ports=tuple(aux.ports(adapter)),
                )
            )
        return result
    finally:
        _release_aux(aux)


class AuxPort:
    """An opened AMD DP/eDP AUX endpoint.

    ``index`` is counted within ports of the requested kind on one physical
    GPU. For example, ``AuxPort("DP", index=1)`` selects the second external
    DP port, regardless of where an eDP port appears in the ADL display table.
    """

    def __init__(self, kind: str, index: int = 0, gpu_index: int = 0) -> None:
        self._aux = None
        self._port = None

        normalized_kind = self._normalize_kind(kind)
        if index < 0 or gpu_index < 0:
            raise ValueError("index and gpu_index must not be negative")

        aux = _acquire_aux()
        try:
            adapters = aux.adapters()
            if gpu_index >= len(adapters):
                raise AuxError(
                    f"GPU index {gpu_index} is unavailable; found {len(adapters)} AMD GPU(s)"
                )
            adapter = adapters[gpu_index]
            matching_ports = [
                port for port in aux.ports(adapter) if port.kind == normalized_kind
            ]
            if index >= len(matching_ports):
                raise AuxError(
                    f"{normalized_kind} port index {index} is unavailable on GPU {gpu_index}; "
                    f"found {len(matching_ports)} matching port(s)"
                )
            self._aux = aux
            self._port = matching_ports[index]
            self._gpu_index = gpu_index
            self._kind_index = index
        except Exception:
            _release_aux(aux)
            raise

    @staticmethod
    def _normalize_kind(kind: str) -> str:
        if not isinstance(kind, str):
            raise TypeError("kind must be 'eDP' or 'DP'")
        normalized = kind.strip().lower()
        if normalized == "edp":
            return "eDP"
        if normalized == "dp":
            return "DP"
        raise ValueError("kind must be 'eDP' or 'DP'")

    def _require_open(self) -> tuple[AmdAux, Port]:
        if self._aux is None or self._port is None:
            raise AuxError("AuxPort is closed")
        return self._aux, self._port

    @property
    def info(self) -> Port:
        """Return the immutable ADL port information."""

        return self._require_open()[1]

    @property
    def identity(self) -> str:
        return self.info.identity

    @property
    def kind(self) -> str:
        return self.info.kind

    @property
    def gpu_index(self) -> int:
        self._require_open()
        return self._gpu_index

    @property
    def index(self) -> int:
        self._require_open()
        return self._kind_index

    def read_dpcd(self, address: int, length: int) -> bytes:
        aux, port = self._require_open()
        return aux.read_dpcd(port, address, length)

    def write_dpcd(self, address: int, data: bytes) -> None:
        aux, port = self._require_open()
        aux.write_dpcd(port, address, data)

    def i2c_read(self, device: int, register: int, length: int) -> bytes:
        aux, port = self._require_open()
        return aux.i2c_read(port, device, register, length)

    def i2c_write(self, device: int, register: int, data: bytes) -> None:
        aux, port = self._require_open()
        aux.i2c_write(port, device, register, data)

    def close(self) -> None:
        if self._aux is not None:
            _release_aux(self._aux)
            self._aux = None
            self._port = None

    def __enter__(self) -> "AuxPort":
        self._require_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            # Interpreter shutdown may have already released module globals.
            pass
