from __future__ import annotations

import ctypes
import threading
import time
from ctypes import POINTER, Structure, byref, c_char, c_int, c_uint8, c_uint32, c_void_p

from .adl import Adapter, AuxError, Port


NVAPI_OK = 0
NVAPI_MAX_PHYSICAL_GPUS = 64
NVAPI_SHORT_STRING_MAX = 64
NV_MONITOR_CONN_TYPE_DP = 7
NV_GPU_DISPLAYIDS_VER1 = 0x00010010
NV_DP_AUX_REQUEST_VERSION = 0x00010028
NV_DP_AUX_REQUEST_SIZE = 0x68
NV_AUX_CHUNK_SIZE = 16
RETRY_COUNT = 10

NVAPI_INITIALIZE_ID = 0x0150E828
NVAPI_UNLOAD_ID = 0xD22BDD7E
NVAPI_ENUM_PHYSICAL_GPUS_ID = 0xE5AC921F
NVAPI_GPU_GET_FULL_NAME_ID = 0xCEEE8E9F
NVAPI_GPU_GET_PCI_IDENTIFIERS_ID = 0x2DDFB66E
NVAPI_GPU_GET_CONNECTED_DISPLAY_IDS_ID = 0x0078DBA2
NVAPI_DISP_DP_AUX_CHANNEL_CONTROL_ID = 0x8EB56969


class _NvGpuDisplayIds(Structure):
    _fields_ = [
        ("version", c_uint32),
        ("connector_type", c_uint32),
        ("display_id", c_uint32),
        ("flags", c_uint32),
    ]


class _NvDpAuxRequest(Structure):
    _fields_ = [
        ("version", c_uint32),
        ("display_id", c_uint32),
        ("command", c_uint32),
        ("address", c_uint32),
        ("data", c_uint8 * NV_AUX_CHUNK_SIZE),
        ("length_field", c_uint32),
        ("result", c_uint32),
        ("reserved", c_uint8 * 0x40),
    ]


assert ctypes.sizeof(_NvGpuDisplayIds) == 0x10
assert ctypes.sizeof(_NvDpAuxRequest) == NV_DP_AUX_REQUEST_SIZE


def _decode_short_string(value: bytes) -> str:
    return bytes(value).split(b"\0", 1)[0].decode("utf-8", errors="replace")


class NvidiaAux:
    """Direct binding to NVIDIA NVAPI DisplayPort AUX functions."""

    def __init__(self) -> None:
        if ctypes.sizeof(c_void_p) != 8:
            raise AuxError("amd_aux requires 64-bit Python")
        self._lock = threading.RLock()
        self._closed = False
        self._nvapi = self._load_nvapi()
        self._bind()
        self._check(self._initialize(), "NVAPI initialization")

    @staticmethod
    def _load_nvapi():
        try:
            return ctypes.CDLL("nvapi64.dll")
        except OSError as error:
            raise AuxError("NVIDIA NVAPI library nvapi64.dll was not found") from error

    def _query(self, interface_id: int) -> int:
        pointer = self._query_interface(interface_id)
        if not pointer:
            raise AuxError(f"NVAPI interface 0x{interface_id:08X} was not found")
        return pointer

    def _bind(self) -> None:
        query = self._nvapi.nvapi_QueryInterface
        query.argtypes = [c_uint32]
        query.restype = c_void_p
        self._query_interface = query
        self._initialize = ctypes.CFUNCTYPE(c_int)(self._query(NVAPI_INITIALIZE_ID))
        self._unload = ctypes.CFUNCTYPE(c_int)(self._query(NVAPI_UNLOAD_ID))
        self._enum_physical_gpus = ctypes.CFUNCTYPE(
            c_int, POINTER(c_void_p), POINTER(c_uint32)
        )(self._query(NVAPI_ENUM_PHYSICAL_GPUS_ID))
        self._gpu_get_full_name = ctypes.CFUNCTYPE(c_int, c_void_p, c_char * NVAPI_SHORT_STRING_MAX)(
            self._query(NVAPI_GPU_GET_FULL_NAME_ID)
        )
        self._gpu_get_pci_identifiers = ctypes.CFUNCTYPE(
            c_int, c_void_p, POINTER(c_uint32), POINTER(c_uint32), POINTER(c_uint32), POINTER(c_uint32)
        )(self._query(NVAPI_GPU_GET_PCI_IDENTIFIERS_ID))
        self._gpu_get_connected_display_ids = ctypes.CFUNCTYPE(
            c_int, c_void_p, POINTER(_NvGpuDisplayIds), POINTER(c_uint32), c_uint32
        )(self._query(NVAPI_GPU_GET_CONNECTED_DISPLAY_IDS_ID))
        self._dp_aux_channel_control = ctypes.CFUNCTYPE(
            c_int, c_uint32, POINTER(_NvDpAuxRequest), c_uint32
        )(self._query(NVAPI_DISP_DP_AUX_CHANNEL_CONTROL_ID))

    @staticmethod
    def _check(rc: int, operation: str) -> None:
        if rc != NVAPI_OK:
            raise AuxError(f"{operation} failed: NVAPI error {rc}")

    @staticmethod
    def _result_text(result: int) -> str:
        return {
            0: "success",
            1: "defer",
            2: "requested data not found",
            0xFF: "timeout",
        }.get(result, f"result {result}")

    def _ensure_open(self) -> None:
        if self._closed:
            raise AuxError("NvidiaAux is closed")

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._unload()
                self._closed = True

    def __enter__(self) -> "NvidiaAux":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _gpu_handles(self) -> list[c_void_p]:
        handles = (c_void_p * NVAPI_MAX_PHYSICAL_GPUS)()
        count = c_uint32()
        self._check(self._enum_physical_gpus(handles, byref(count)), "NVIDIA GPU enumeration")
        return [handles[index] for index in range(count.value)]

    def adapters(self) -> list[Adapter]:
        with self._lock:
            self._ensure_open()
            adapters = []
            for index, handle in enumerate(self._gpu_handles()):
                name = (c_char * NVAPI_SHORT_STRING_MAX)()
                rc = self._gpu_get_full_name(handle, name)
                display_name = _decode_short_string(name) if rc == NVAPI_OK else "NVIDIA GPU"
                bus = c_uint32()
                device = c_uint32()
                pci_id = c_uint32()
                subsystem_id = c_uint32()
                rc = self._gpu_get_pci_identifiers(
                    handle, byref(device), byref(subsystem_id), byref(pci_id), byref(bus)
                )
                if rc != NVAPI_OK:
                    bus.value = index
                    device.value = 0
                adapters.append(
                    Adapter(
                        index=index,
                        name=display_name,
                        display_name=display_name,
                        bus=bus.value,
                        device=device.value,
                        function=0,
                        backend="NVIDIA",
                    )
                )
            return adapters

    def ports(self, adapter: Adapter, connected_only: bool = True) -> list[Port]:
        with self._lock:
            self._ensure_open()
            handles = self._gpu_handles()
            if adapter.index >= len(handles):
                raise AuxError(f"NVIDIA GPU index {adapter.index} is unavailable")
            handle = handles[adapter.index]
            count = c_uint32()
            self._check(
                self._gpu_get_connected_display_ids(handle, None, byref(count), 0),
                "NVIDIA display ID count",
            )
            if count.value == 0:
                return []
            raw = (_NvGpuDisplayIds * count.value)()
            for item in raw:
                item.version = NV_GPU_DISPLAYIDS_VER1
            self._check(
                self._gpu_get_connected_display_ids(handle, raw, byref(count), 0),
                "NVIDIA display ID enumeration",
            )
            result = []
            for position in range(count.value):
                item = raw[position]
                connected = bool(item.flags & (1 << 6))
                physically_connected = bool(item.flags & (1 << 17))
                if connected_only and not connected:
                    continue
                if connected_only and not physically_connected:
                    continue
                if item.connector_type != NV_MONITOR_CONN_TYPE_DP:
                    continue
                result.append(
                    Port(
                        adapter=adapter,
                        index=position,
                        logical_display_index=item.display_id,
                        physical_display_index=position,
                        name=f"NVIDIA Display 0x{item.display_id:08X}",
                        manufacturer="",
                        display_type=0,
                        output_type=item.connector_type,
                        connector=item.connector_type,
                        connected=connected,
                        backend="nvapi",
                    )
                )
            return result

    @staticmethod
    def _validate_port(port: Port) -> None:
        if not port.connected:
            raise ValueError("port is not connected")

    def _aux(self, port: Port, command: int, address: int, data: bytes, length_field: int) -> bytes:
        self._validate_port(port)
        request = _NvDpAuxRequest()
        request.version = NV_DP_AUX_REQUEST_VERSION
        request.display_id = port.logical_display_index
        request.command = command
        request.address = address
        request.length_field = length_field
        if data:
            request.data[: len(data)] = data
        rc = -1
        for _ in range(RETRY_COUNT):
            rc = self._dp_aux_channel_control(port.logical_display_index, byref(request), NV_DP_AUX_REQUEST_SIZE)
            if rc == NVAPI_OK and request.result == 0:
                break
            time.sleep(0.01)
        self._check(rc, "NVIDIA AUX transaction")
        if request.result != 0:
            raise AuxError(f"NVIDIA AUX transaction failed: {self._result_text(request.result)}")
        return bytes(request.data)

    def read_dpcd(self, port: Port, address: int, length: int) -> bytes:
        if length <= 0:
            raise ValueError("length must be positive")
        if not 0 <= address <= 0xFFFFF:
            raise ValueError("DPCD address must be in range 0x00000..0xFFFFF")
        with self._lock:
            self._ensure_open()
            output = bytearray()
            while len(output) < length:
                size = min(NV_AUX_CHUNK_SIZE, length - len(output))
                output += self._aux(port, 1, address + len(output), b"", size - 1)[:size]
            return bytes(output)

    def write_dpcd(self, port: Port, address: int, data: bytes) -> None:
        data = bytes(data)
        if not data:
            raise ValueError("data must not be empty")
        if not 0 <= address <= 0xFFFFF:
            raise ValueError("DPCD address must be in range 0x00000..0xFFFFF")
        with self._lock:
            self._ensure_open()
            for offset in range(0, len(data), NV_AUX_CHUNK_SIZE):
                chunk = data[offset : offset + NV_AUX_CHUNK_SIZE]
                self._aux(port, 0, address + offset, chunk, len(chunk) - 1)

    @staticmethod
    def _dev7(address: int) -> int:
        if not 0 <= address <= 0xFF:
            raise ValueError("I2C address must fit in one byte")
        return address >> 1 if address >= 0x80 else address & 0x7F

    @classmethod
    def _i2c_write_address(cls, address: int) -> int:
        return cls._dev7(address) << 1

    def i2c_read(self, port: Port, device: int, register: int, length: int) -> bytes:
        if length <= 0 or not 0 <= register <= 0xFF:
            raise ValueError("length must be positive and register must fit in one byte")
        device_address = self._i2c_write_address(device)
        with self._lock:
            self._ensure_open()
            self._aux(port, 5, device_address, bytes((register,)), 0)
            output = bytearray()
            while len(output) < length:
                size = min(NV_AUX_CHUNK_SIZE, length - len(output))
                final = len(output) + size >= length
                command = 3 if final else 6
                output += self._aux(port, command, device_address, b"", size - 1)[:size]
            return bytes(output)

    def i2c_write(self, port: Port, device: int, register: int, data: bytes) -> None:
        data = bytes(data)
        if not data or not 0 <= register <= 0xFF:
            raise ValueError("data must not be empty and register must fit in one byte")
        dev7 = self._dev7(device)
        device_address = dev7 << 1
        with self._lock:
            self._ensure_open()
            if dev7 == 0x30:
                if len(data) != 1:
                    raise ValueError("EDID segment-pointer writes require exactly one byte")
                self._aux(port, 2, device_address, data, len(data))
                return
            for offset in range(0, len(data), NV_AUX_CHUNK_SIZE):
                chunk = data[offset : offset + NV_AUX_CHUNK_SIZE]
                payload = bytes(((register + offset) & 0xFF,)) + chunk
                self._aux(port, 2, device_address, payload, len(chunk))
