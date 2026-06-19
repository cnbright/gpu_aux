from __future__ import annotations

import ctypes
import threading
import time
from dataclasses import dataclass
from ctypes import POINTER, Structure, byref, c_char, c_int, c_uint8, c_uint32, c_void_p


ADL_OK = 0
ADL_DISPLAY_CONNECTED = 1
AMD_VENDOR_IDS = {1002, 0x1002}
ADL_CONNECTOR_DISPLAY_PORT = 15
ADL_CONNECTOR_EDP = 16
AUX_CONNECTORS = {ADL_CONNECTOR_DISPLAY_PORT, ADL_CONNECTOR_EDP}
AUX_CHUNK_SIZE = 16
RETRY_COUNT = 10


class AuxError(RuntimeError):
    """Raised when ADL or an AUX transaction fails."""


class _ADLAdapterInfo(Structure):
    _fields_ = [
        ("iSize", c_int),
        ("iAdapterIndex", c_int),
        ("strUDID", c_char * 256),
        ("iBusNumber", c_int),
        ("iDeviceNumber", c_int),
        ("iFunctionNumber", c_int),
        ("iVendorID", c_int),
        ("strAdapterName", c_char * 256),
        ("strDisplayName", c_char * 256),
        ("iPresent", c_int),
        ("iExist", c_int),
        ("strDriverPath", c_char * 256),
        ("strDriverPathExt", c_char * 256),
        ("strPNPString", c_char * 256),
        ("iOSDisplayIndex", c_int),
    ]


class _ADLDisplayID(Structure):
    _fields_ = [
        ("iDisplayLogicalIndex", c_int),
        ("iDisplayPhysicalIndex", c_int),
        ("iDisplayLogicalAdapterIndex", c_int),
        ("iDisplayPhysicalAdapterIndex", c_int),
    ]


class _ADLDisplayInfo(Structure):
    _fields_ = [
        ("displayID", _ADLDisplayID),
        ("iDisplayControllerIndex", c_int),
        ("strDisplayName", c_char * 256),
        ("strDisplayManufacturerName", c_char * 256),
        ("iDisplayType", c_int),
        ("iDisplayOutputType", c_int),
        ("iDisplayConnector", c_int),
        ("iDisplayInfoMask", c_int),
        ("iDisplayInfoValue", c_int),
    ]


class _NativeAuxRequest(Structure):
    _fields_ = [
        ("size", c_uint32),
        ("result", c_uint32),
        ("operation", c_uint32),
        ("address", c_uint32),
        ("data_size", c_uint32),
        ("data", c_uint8 * AUX_CHUNK_SIZE),
    ]


assert ctypes.sizeof(_ADLAdapterInfo) == 0x624
assert ctypes.sizeof(_ADLDisplayInfo) == 0x228
assert ctypes.sizeof(_NativeAuxRequest) == 0x24


def _text(value: bytes) -> str:
    return value.split(b"\0", 1)[0].decode("utf-8", errors="replace")


@dataclass(frozen=True)
class Adapter:
    index: int
    name: str
    display_name: str
    bus: int
    device: int
    function: int
    backend: str = "AMD"


@dataclass(frozen=True)
class Port:
    adapter: Adapter
    index: int
    logical_display_index: int
    physical_display_index: int
    name: str
    manufacturer: str
    display_type: int
    output_type: int
    connector: int
    connected: bool
    backend: str = "adl"

    @property
    def identity(self) -> str:
        return f"{self.backend}:{self.adapter.index}:{self.logical_display_index}"

    @property
    def kind(self) -> str:
        return "eDP" if self.connector == ADL_CONNECTOR_EDP else "DP"


class AmdAux:
    """Direct binding to AMD ADL AUX and DDC functions.

    ADL is process-global, so one instance serializes all transactions.
    """

    def __init__(self) -> None:
        if ctypes.sizeof(c_void_p) != 8:
            raise AuxError("amd_aux requires 64-bit Python")
        self._lock = threading.RLock()
        self._closed = False
        self._crt = ctypes.CDLL("msvcrt")
        self._crt.malloc.argtypes = [ctypes.c_size_t]
        self._crt.malloc.restype = c_void_p
        self._crt.free.argtypes = [c_void_p]
        self._alloc_type = ctypes.CFUNCTYPE(c_void_p, c_int)
        self._allocator = self._alloc_type(self._allocate)
        self._adl = self._load_adl()
        self._bind()
        self._check(self._adl.ADL_Main_Control_Create(self._allocator, 1), "ADL initialization")

    @staticmethod
    def _load_adl():
        for name in ("atiadlxx.dll", "atiadlxy.dll"):
            try:
                return ctypes.CDLL(name)
            except OSError:
                pass
        raise AuxError("AMD ADL library atiadlxx.dll was not found")

    def _allocate(self, size: int):
        return self._crt.malloc(size)

    def _bind(self) -> None:
        adl = self._adl
        adl.ADL_Main_Control_Create.argtypes = [self._alloc_type, c_int]
        adl.ADL_Main_Control_Create.restype = c_int
        adl.ADL_Main_Control_Destroy.argtypes = []
        adl.ADL_Main_Control_Destroy.restype = c_int
        adl.ADL_Adapter_NumberOfAdapters_Get.argtypes = [POINTER(c_int)]
        adl.ADL_Adapter_NumberOfAdapters_Get.restype = c_int
        adl.ADL_Adapter_AdapterInfo_Get.argtypes = [c_void_p, c_int]
        adl.ADL_Adapter_AdapterInfo_Get.restype = c_int
        adl.ADL_Display_DisplayInfo_Get.argtypes = [c_int, POINTER(c_int), POINTER(c_void_p), c_int]
        adl.ADL_Display_DisplayInfo_Get.restype = c_int
        adl.ADL_Display_NativeAUXChannel_Access.argtypes = [c_int, c_int, POINTER(_NativeAuxRequest)]
        adl.ADL_Display_NativeAUXChannel_Access.restype = c_int
        adl.ADL_Display_DDCBlockAccess_Get.argtypes = [
            c_int, c_int, c_int, c_int, c_int, c_void_p, POINTER(c_int), c_void_p
        ]
        adl.ADL_Display_DDCBlockAccess_Get.restype = c_int

    @staticmethod
    def _check(rc: int, operation: str) -> None:
        if rc != ADL_OK:
            raise AuxError(f"{operation} failed: ADL error {rc}")

    def _ensure_open(self) -> None:
        if self._closed:
            raise AuxError("AmdAux is closed")

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._adl.ADL_Main_Control_Destroy()
                self._closed = True

    def __enter__(self) -> "AmdAux":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def adapters(self) -> list[Adapter]:
        with self._lock:
            self._ensure_open()
            count = c_int()
            self._check(self._adl.ADL_Adapter_NumberOfAdapters_Get(byref(count)), "adapter enumeration")
            raw = (_ADLAdapterInfo * count.value)()
            for item in raw:
                item.iSize = ctypes.sizeof(_ADLAdapterInfo)
            self._check(self._adl.ADL_Adapter_AdapterInfo_Get(raw, ctypes.sizeof(raw)), "adapter information")
            adapters = [
                Adapter(
                    index=item.iAdapterIndex,
                    name=_text(item.strAdapterName),
                    display_name=_text(item.strDisplayName),
                    bus=item.iBusNumber,
                    device=item.iDeviceNumber,
                    function=item.iFunctionNumber,
                )
                for item in raw
                if item.iPresent == 1 and item.iVendorID in AMD_VENDOR_IDS
            ]
            # ADL exposes one logical adapter per Windows DISPLAYx even when all
            # entries refer to the same physical GPU. AUX ports belong to the
            # physical PCI function, so retain one representative per BDF.
            unique = {}
            for adapter in adapters:
                unique.setdefault((adapter.bus, adapter.device, adapter.function), adapter)
            return list(unique.values())

    def ports(self, adapter: Adapter, connected_only: bool = True) -> list[Port]:
        with self._lock:
            self._ensure_open()
            count = c_int()
            pointer = c_void_p()
            self._check(
                self._adl.ADL_Display_DisplayInfo_Get(adapter.index, byref(count), byref(pointer), 1),
                "display enumeration",
            )
            try:
                if not pointer.value or count.value <= 0:
                    return []
                raw = ctypes.cast(pointer, POINTER(_ADLDisplayInfo))
                result = []
                for position in range(count.value):
                    item = raw[position]
                    connected = bool(item.iDisplayInfoValue & ADL_DISPLAY_CONNECTED)
                    if item.iDisplayConnector not in AUX_CONNECTORS:
                        continue
                    if connected_only and not connected:
                        continue
                    result.append(
                        Port(
                            adapter=adapter,
                            index=position,
                            logical_display_index=item.displayID.iDisplayLogicalIndex,
                            physical_display_index=item.displayID.iDisplayPhysicalIndex,
                            name=_text(item.strDisplayName),
                            manufacturer=_text(item.strDisplayManufacturerName),
                            display_type=item.iDisplayType,
                            output_type=item.iDisplayOutputType,
                            connector=item.iDisplayConnector,
                            connected=connected,
                        )
                    )
                return result
            finally:
                if pointer.value:
                    self._crt.free(pointer)

    @staticmethod
    def _validate_port(port: Port) -> None:
        if not port.connected:
            raise ValueError("port is not connected")

    def _native_aux(self, port: Port, operation: int, address: int, data: bytes) -> bytes:
        self._validate_port(port)
        if not 0 <= address <= 0xFFFFF:
            raise ValueError("DPCD address must be in range 0x00000..0xFFFFF")
        request = _NativeAuxRequest()
        request.size = ctypes.sizeof(request)
        request.operation = operation
        request.address = address
        request.data_size = len(data)
        if operation == 1:
            request.data[: len(data)] = data
        rc = -1
        for _ in range(RETRY_COUNT):
            rc = self._adl.ADL_Display_NativeAUXChannel_Access(
                port.adapter.index, port.logical_display_index, byref(request)
            )
            if rc == ADL_OK:
                break
            time.sleep(0.01)
        self._check(rc, "DPCD read" if operation == 0 else "DPCD write")
        if operation == 0 and request.data_size < len(data):
            raise AuxError(f"DPCD read returned {request.data_size} of {len(data)} bytes")
        return bytes(request.data[: len(data)])

    def read_dpcd(self, port: Port, address: int, length: int) -> bytes:
        if length <= 0:
            raise ValueError("length must be positive")
        with self._lock:
            self._ensure_open()
            output = bytearray()
            while len(output) < length:
                size = min(AUX_CHUNK_SIZE, length - len(output))
                output += self._native_aux(port, 0, address + len(output), bytes(size))
            return bytes(output)

    def write_dpcd(self, port: Port, address: int, data: bytes) -> None:
        data = bytes(data)
        if not data:
            raise ValueError("data must not be empty")
        with self._lock:
            self._ensure_open()
            for offset in range(0, len(data), AUX_CHUNK_SIZE):
                self._native_aux(port, 1, address + offset, data[offset : offset + AUX_CHUNK_SIZE])

    @staticmethod
    def _dev7(address: int) -> int:
        if not 0 <= address <= 0xFF:
            raise ValueError("I2C address must fit in one byte")
        return address >> 1 if address >= 0x80 else address & 0x7F

    def _ddc(self, port: Port, send: bytes, receive_length: int) -> bytes:
        self._validate_port(port)
        send_buffer = (c_uint8 * len(send)).from_buffer_copy(send)
        receive_buffer = (c_uint8 * receive_length)() if receive_length else None
        receive_size = c_int(receive_length)
        rc = -1
        for _ in range(RETRY_COUNT):
            receive_size.value = receive_length
            rc = self._adl.ADL_Display_DDCBlockAccess_Get(
                port.adapter.index,
                port.logical_display_index,
                0,
                0,
                len(send),
                send_buffer,
                byref(receive_size),
                receive_buffer,
            )
            if rc == ADL_OK:
                break
            time.sleep(0.01)
        self._check(rc, "I2C-over-AUX transaction")
        if receive_size.value < receive_length:
            raise AuxError(f"I2C-over-AUX returned {receive_size.value} of {receive_length} bytes")
        return bytes(receive_buffer) if receive_buffer is not None else b""

    def i2c_read(self, port: Port, device: int, register: int, length: int) -> bytes:
        if length <= 0 or not 0 <= register <= 0xFF:
            raise ValueError("length must be positive and register must fit in one byte")
        with self._lock:
            self._ensure_open()
            output = bytearray()
            read_address = (self._dev7(device) << 1) | 1
            while len(output) < length:
                size = min(AUX_CHUNK_SIZE, length - len(output))
                output += self._ddc(port, bytes((read_address, (register + len(output)) & 0xFF)), size)
            return bytes(output)

    def i2c_write(self, port: Port, device: int, register: int, data: bytes) -> None:
        data = bytes(data)
        if not data or not 0 <= register <= 0xFF:
            raise ValueError("data must not be empty and register must fit in one byte")
        with self._lock:
            self._ensure_open()
            write_address = self._dev7(device) << 1
            if self._dev7(device) == 0x30:
                if len(data) != 1:
                    raise ValueError("EDID segment-pointer writes require exactly one byte")
                self._ddc(port, bytes((write_address, data[0])), 0)
                return
            for offset in range(0, len(data), AUX_CHUNK_SIZE):
                chunk = data[offset : offset + AUX_CHUNK_SIZE]
                self._ddc(port, bytes((write_address, (register + offset) & 0xFF)) + chunk, 0)
