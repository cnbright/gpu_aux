"""Object-oriented public API for selecting and using one AUX port."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from .adl import Adapter, AmdAux, AuxError, Port
from .intel import IntelAux
from .nvapi import NvidiaAux


_context_lock = threading.RLock()
_contexts = {}


def _normalize_backend(backend: str) -> str:
    if not isinstance(backend, str):
        raise TypeError("backend must be 'AMD', 'NVIDIA', or 'INTEL'")
    normalized = backend.strip().upper()
    if normalized in {"AMD", "NVIDIA", "INTEL"}:
        return normalized
    raise ValueError("backend must be 'AMD', 'NVIDIA', or 'INTEL'")


def _create_aux(backend: str):
    if backend == "AMD":
        return AmdAux()
    if backend == "NVIDIA":
        return NvidiaAux()
    if backend == "INTEL":
        return IntelAux()
    raise ValueError("backend must be 'AMD', 'NVIDIA', or 'INTEL'")


def _acquire_aux(backend: str):
    normalized_backend = _normalize_backend(backend)
    with _context_lock:
        context = _contexts.get(normalized_backend)
        if context is None:
            context = [_create_aux(normalized_backend), 0]
            _contexts[normalized_backend] = context
        context[1] += 1
        return context[0]


def _release_aux(backend: str, aux) -> None:
    normalized_backend = _normalize_backend(backend)
    with _context_lock:
        context = _contexts.get(normalized_backend)
        if context is None or aux is not context[0] or context[1] <= 0:
            return
        context[1] -= 1
        if context[1] == 0:
            aux.close()
            del _contexts[normalized_backend]


@dataclass(frozen=True)
class GpuPorts:
    """A physical GPU and a snapshot of its connected DP/eDP ports."""

    gpu_index: int
    adapter: Adapter
    ports: tuple[Port, ...]


def enumerate_gpus(backend: str) -> list[Adapter]:
    """Return physical GPUs for one backend without creating an ``AuxPort``."""

    normalized_backend = _normalize_backend(backend)
    aux = _acquire_aux(normalized_backend)
    try:
        return aux.adapters()
    finally:
        _release_aux(normalized_backend, aux)


def enumerate_ports(backend: str, gpu_index: int = 0) -> list[Port]:
    """Return connected DP/eDP ports on one GPU without creating an ``AuxPort``."""

    if gpu_index < 0:
        raise ValueError("gpu_index must not be negative")
    normalized_backend = _normalize_backend(backend)
    aux = _acquire_aux(normalized_backend)
    try:
        adapters = aux.adapters()
        if gpu_index >= len(adapters):
            raise AuxError(
                f"GPU index {gpu_index} is unavailable for {normalized_backend}; "
                f"found {len(adapters)} GPU(s)"
            )
        return aux.ports(adapters[gpu_index])
    finally:
        _release_aux(normalized_backend, aux)


def enumerate_gpus_and_ports(backend: str) -> list[GpuPorts]:
    """Return a combined GPU/port snapshot without creating an ``AuxPort``."""

    normalized_backend = _normalize_backend(backend)
    aux = _acquire_aux(normalized_backend)
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
        _release_aux(normalized_backend, aux)


class AuxPort:
    """An opened DP/eDP AUX endpoint.

    ``index`` is counted within ports of the requested kind on one physical
    GPU. For example, ``AuxPort("DP", index=1, backend="NVIDIA")`` selects the
    second external DP port on the first NVIDIA GPU.
    """

    def __init__(self, kind: str, index: int = 0, gpu_index: int = 0, *, backend: str) -> None:
        self._aux = None
        self._port = None

        normalized_backend = _normalize_backend(backend)
        normalized_kind = self._normalize_kind(kind)
        if index < 0 or gpu_index < 0:
            raise ValueError("index and gpu_index must not be negative")

        aux = _acquire_aux(normalized_backend)
        try:
            adapters = aux.adapters()
            if gpu_index >= len(adapters):
                raise AuxError(
                    f"GPU index {gpu_index} is unavailable for {normalized_backend}; "
                    f"found {len(adapters)} GPU(s)"
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
            self._backend = normalized_backend
            self._gpu_index = gpu_index
            self._kind_index = index
        except Exception:
            _release_aux(normalized_backend, aux)
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
        """Return the immutable port information."""

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
    def backend(self) -> str:
        self._require_open()
        return self._backend

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

    def i2c_read(self, device: int, length: int) -> bytes:
        aux, port = self._require_open()
        return aux.i2c_read(port, device, length)

    def i2c_write(self, device: int, data: bytes) -> None:
        aux, port = self._require_open()
        aux.i2c_write(port, device, data)

    def close(self) -> None:
        if self._aux is not None:
            _release_aux(self._backend, self._aux)
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
