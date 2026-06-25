from __future__ import annotations

import ctypes
import threading
import time
from ctypes import (
    POINTER,
    Structure,
    Union,
    byref,
    c_bool,
    c_char,
    c_float,
    c_int64,
    c_uint8,
    c_uint16,
    c_uint32,
    c_uint64,
    c_void_p,
)

from .adl import ADL_CONNECTOR_DISPLAY_PORT, ADL_CONNECTOR_EDP, Adapter, AuxError, Port


CTL_RESULT_SUCCESS = 0
CTL_IMPL_VERSION = 0x00010001
CTL_MAX_DEVICE_NAME_LEN = 100
CTL_MAX_RESERVED_SIZE = 108
CTL_DISPLAY_ATTACHED = 1 << 1
CTL_DISPLAY_OUTPUT_TYPES_DISPLAYPORT = 1
CTL_ENCODER_INTERNAL_DISPLAY = 1 << 0
CTL_AUX_MAX_DATA_SIZE = 132
CTL_AUX_CHUNK_SIZE = 16
CTL_OPERATION_TYPE_READ = 1
CTL_OPERATION_TYPE_WRITE = 2
CTL_AUX_FLAG_NATIVE_AUX = 1 << 0
CTL_AUX_FLAG_I2C_AUX = 1 << 1
CTL_AUX_FLAG_I2C_AUX_MOT = 1 << 2
RETRY_COUNT = 10


class _CtlApplicationId(Structure):
    _fields_ = [
        ("Data1", c_uint32),
        ("Data2", c_uint16),
        ("Data3", c_uint16),
        ("Data4", c_uint8 * 8),
    ]


class _CtlInitArgs(Structure):
    _fields_ = [
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("AppVersion", c_uint32),
        ("flags", c_uint32),
        ("SupportedVersion", c_uint32),
        ("ApplicationUID", _CtlApplicationId),
    ]


class _CtlFirmwareVersion(Structure):
    _fields_ = [
        ("major_version", c_uint64),
        ("minor_version", c_uint64),
        ("build_number", c_uint64),
    ]


class _CtlAdapterBdf(Structure):
    _fields_ = [
        ("bus", c_uint8),
        ("device", c_uint8),
        ("function", c_uint8),
    ]


class _CtlDeviceAdapterProperties(Structure):
    _fields_ = [
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("pDeviceID", c_void_p),
        ("device_id_size", c_uint32),
        ("device_type", c_uint32),
        ("supported_subfunction_flags", c_uint32),
        ("driver_version", c_uint64),
        ("firmware_version", _CtlFirmwareVersion),
        ("pci_vendor_id", c_uint32),
        ("pci_device_id", c_uint32),
        ("rev_id", c_uint32),
        ("num_eus_per_sub_slice", c_uint32),
        ("num_sub_slices_per_slice", c_uint32),
        ("num_slices", c_uint32),
        ("name", c_char * CTL_MAX_DEVICE_NAME_LEN),
        ("graphics_adapter_properties", c_uint32),
        ("Frequency", c_uint32),
        ("pci_subsys_id", c_uint16),
        ("pci_subsys_vendor_id", c_uint16),
        ("adapter_bdf", _CtlAdapterBdf),
        ("num_xe_cores", c_uint32),
        ("reserved", c_char * CTL_MAX_RESERVED_SIZE),
    ]


class _CtlGenericVoidDatatype(Structure):
    _fields_ = [
        ("pData", c_void_p),
        ("size", c_uint32),
    ]


class _CtlOsDisplayEncoderIdentifier(Union):
    _fields_ = [
        ("WindowsDisplayEncoderID", c_uint32),
        ("DisplayEncoderID", _CtlGenericVoidDatatype),
    ]


class _CtlRevisionDatatype(Structure):
    _fields_ = [
        ("major_version", c_uint8),
        ("minor_version", c_uint8),
        ("revision_version", c_uint8),
    ]


class _CtlDisplayTiming(Structure):
    _fields_ = [
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("PixelClock", c_uint64),
        ("HActive", c_uint32),
        ("VActive", c_uint32),
        ("HTotal", c_uint32),
        ("VTotal", c_uint32),
        ("HBlank", c_uint32),
        ("VBlank", c_uint32),
        ("HSync", c_uint32),
        ("VSync", c_uint32),
        ("RefreshRate", c_float),
        ("SignalStandard", c_uint32),
        ("VicId", c_uint8),
    ]


class _CtlDisplayProperties(Structure):
    _fields_ = [
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("Os_display_encoder_handle", _CtlOsDisplayEncoderIdentifier),
        ("Type", c_uint32),
        ("AttachedDisplayMuxType", c_uint32),
        ("ProtocolConverterOutput", c_uint32),
        ("SupportedSpec", _CtlRevisionDatatype),
        ("SupportedOutputBPCFlags", c_uint32),
        ("ProtocolConverterType", c_uint32),
        ("DisplayConfigFlags", c_uint32),
        ("FeatureEnabledFlags", c_uint32),
        ("FeatureSupportedFlags", c_uint32),
        ("AdvancedFeatureEnabledFlags", c_uint32),
        ("AdvancedFeatureSupportedFlags", c_uint32),
        ("Display_Timing_Info", _CtlDisplayTiming),
        ("ReservedFields", c_uint32 * 16),
    ]


class _CtlAdapterDisplayEncoderProperties(Structure):
    _fields_ = [
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("Os_display_encoder_handle", _CtlOsDisplayEncoderIdentifier),
        ("Type", c_uint32),
        ("IsOnBoardProtocolConverterOutputPresent", c_bool),
        ("SupportedSpec", _CtlRevisionDatatype),
        ("SupportedOutputBPCFlags", c_uint32),
        ("EncoderConfigFlags", c_uint32),
        ("FeatureSupportedFlags", c_uint32),
        ("AdvancedFeatureSupportedFlags", c_uint32),
        ("ReservedFields", c_uint32 * 16),
    ]


class _CtlPciAddress(Structure):
    _fields_ = [
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("domain", c_uint32),
        ("bus", c_uint32),
        ("device", c_uint32),
        ("function", c_uint32),
    ]


class _CtlPciSpeed(Structure):
    _fields_ = [
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("gen", c_uint32),
        ("width", c_uint32),
        ("maxBandwidth", c_int64),
    ]


class _CtlPciProperties(Structure):
    _fields_ = [
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("address", _CtlPciAddress),
        ("maxSpeed", _CtlPciSpeed),
        ("resizable_bar_supported", c_bool),
        ("resizable_bar_enabled", c_bool),
    ]


class _CtlAuxAccessArgs(Structure):
    _fields_ = [
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("OpType", c_uint32),
        ("Flags", c_uint32),
        ("Address", c_uint32),
        ("RAD", c_uint64),
        ("PortID", c_uint32),
        ("DataSize", c_uint32),
        ("Data", c_uint8 * CTL_AUX_MAX_DATA_SIZE),
    ]


assert ctypes.sizeof(_CtlApplicationId) == 0x10
assert ctypes.sizeof(_CtlInitArgs) == 0x24
assert ctypes.sizeof(_CtlDeviceAdapterProperties) == 0x140
assert ctypes.sizeof(_CtlDisplayProperties) == 0xC8
assert ctypes.sizeof(_CtlAdapterDisplayEncoderProperties) == 0x70
assert ctypes.sizeof(_CtlPciProperties) == 0x40
assert ctypes.sizeof(_CtlAuxAccessArgs) == 0xB0


def _text(value: bytes) -> str:
    return value.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def _handle_value(handle) -> int:
    value = handle.value if isinstance(handle, c_void_p) else handle
    if value is None:
        raise AuxError("IGCL returned a null handle")
    return int(value)


class IntelAux:
    """Direct binding to Intel IGCL AUX access functions."""

    def __init__(self) -> None:
        if ctypes.sizeof(c_void_p) != 8:
            raise AuxError("gpu_aux requires 64-bit Python")
        self._lock = threading.RLock()
        self._closed = False
        self._ctl = self._load_control_lib()
        self._bind()
        init_args = _CtlInitArgs()
        init_args.Size = ctypes.sizeof(init_args)
        init_args.AppVersion = CTL_IMPL_VERSION
        self._handle = c_void_p()
        self._check(self._ctl.ctlInit(byref(init_args), byref(self._handle)), "IGCL initialization")

    @staticmethod
    def _load_control_lib():
        try:
            return ctypes.CDLL("ControlLib.dll")
        except OSError as error:
            raise AuxError("Intel IGCL library ControlLib.dll was not found") from error

    def _bind(self) -> None:
        ctl = self._ctl
        ctl.ctlInit.argtypes = [POINTER(_CtlInitArgs), POINTER(c_void_p)]
        ctl.ctlInit.restype = c_uint32
        ctl.ctlClose.argtypes = [c_void_p]
        ctl.ctlClose.restype = c_uint32
        ctl.ctlEnumerateDevices.argtypes = [c_void_p, POINTER(c_uint32), POINTER(c_void_p)]
        ctl.ctlEnumerateDevices.restype = c_uint32
        ctl.ctlEnumerateDisplayOutputs.argtypes = [c_void_p, POINTER(c_uint32), POINTER(c_void_p)]
        ctl.ctlEnumerateDisplayOutputs.restype = c_uint32
        ctl.ctlGetDeviceProperties.argtypes = [c_void_p, POINTER(_CtlDeviceAdapterProperties)]
        ctl.ctlGetDeviceProperties.restype = c_uint32
        ctl.ctlGetDisplayProperties.argtypes = [c_void_p, POINTER(_CtlDisplayProperties)]
        ctl.ctlGetDisplayProperties.restype = c_uint32
        ctl.ctlGetAdaperDisplayEncoderProperties.argtypes = [
            c_void_p,
            POINTER(_CtlAdapterDisplayEncoderProperties),
        ]
        ctl.ctlGetAdaperDisplayEncoderProperties.restype = c_uint32
        ctl.ctlPciGetProperties.argtypes = [c_void_p, POINTER(_CtlPciProperties)]
        ctl.ctlPciGetProperties.restype = c_uint32
        ctl.ctlAUXAccess.argtypes = [c_void_p, POINTER(_CtlAuxAccessArgs)]
        ctl.ctlAUXAccess.restype = c_uint32

    @staticmethod
    def _check(rc: int, operation: str) -> None:
        if rc != CTL_RESULT_SUCCESS:
            raise AuxError(f"{operation} failed: IGCL error 0x{rc:08X}")

    def _ensure_open(self) -> None:
        if self._closed:
            raise AuxError("IntelAux is closed")

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._ctl.ctlClose(self._handle)
                self._closed = True

    def __enter__(self) -> "IntelAux":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _device_handles(self) -> list[c_void_p]:
        count = c_uint32()
        self._check(self._ctl.ctlEnumerateDevices(self._handle, byref(count), None), "Intel GPU count")
        if count.value == 0:
            return []
        handles = (c_void_p * count.value)()
        self._check(
            self._ctl.ctlEnumerateDevices(self._handle, byref(count), handles),
            "Intel GPU enumeration",
        )
        return [handles[index] for index in range(count.value)]

    def _device_properties(self, handle: c_void_p) -> _CtlDeviceAdapterProperties:
        properties = _CtlDeviceAdapterProperties()
        properties.Size = ctypes.sizeof(properties)
        properties.Version = 2
        rc = self._ctl.ctlGetDeviceProperties(handle, byref(properties))
        if rc == CTL_RESULT_SUCCESS:
            return properties
        properties = _CtlDeviceAdapterProperties()
        properties.Size = ctypes.sizeof(properties)
        self._check(self._ctl.ctlGetDeviceProperties(handle, byref(properties)), "Intel GPU properties")
        return properties

    def _pci_bdf(self, handle: c_void_p, properties: _CtlDeviceAdapterProperties) -> tuple[int, int, int]:
        pci = _CtlPciProperties()
        pci.Size = ctypes.sizeof(pci)
        pci.address.Size = ctypes.sizeof(pci.address)
        pci.maxSpeed.Size = ctypes.sizeof(pci.maxSpeed)
        rc = self._ctl.ctlPciGetProperties(handle, byref(pci))
        if rc == CTL_RESULT_SUCCESS:
            return pci.address.bus, pci.address.device, pci.address.function
        return properties.adapter_bdf.bus, properties.adapter_bdf.device, properties.adapter_bdf.function

    def adapters(self) -> list[Adapter]:
        with self._lock:
            self._ensure_open()
            adapters = []
            for index, handle in enumerate(self._device_handles()):
                properties = self._device_properties(handle)
                bus, device, function = self._pci_bdf(handle, properties)
                name = _text(properties.name) or f"Intel GPU {index}"
                adapters.append(
                    Adapter(
                        index=index,
                        name=name,
                        display_name=name,
                        bus=bus,
                        device=device,
                        function=function,
                        backend="INTEL",
                    )
                )
            return adapters

    def _display_handles(self, adapter: Adapter) -> list[c_void_p]:
        handles = self._device_handles()
        if adapter.index >= len(handles):
            raise AuxError(f"Intel GPU index {adapter.index} is unavailable")
        device_handle = handles[adapter.index]
        count = c_uint32()
        self._check(
            self._ctl.ctlEnumerateDisplayOutputs(device_handle, byref(count), None),
            "Intel display count",
        )
        if count.value == 0:
            return []
        output_handles = (c_void_p * count.value)()
        self._check(
            self._ctl.ctlEnumerateDisplayOutputs(device_handle, byref(count), output_handles),
            "Intel display enumeration",
        )
        return [output_handles[index] for index in range(count.value)]

    def _display_properties(self, handle: c_void_p) -> _CtlDisplayProperties:
        properties = _CtlDisplayProperties()
        properties.Size = ctypes.sizeof(properties)
        self._check(self._ctl.ctlGetDisplayProperties(handle, byref(properties)), "Intel display properties")
        return properties

    def _encoder_properties(self, handle: c_void_p) -> _CtlAdapterDisplayEncoderProperties:
        properties = _CtlAdapterDisplayEncoderProperties()
        properties.Size = ctypes.sizeof(properties)
        self._check(
            self._ctl.ctlGetAdaperDisplayEncoderProperties(handle, byref(properties)),
            "Intel display encoder properties",
        )
        return properties

    def ports(self, adapter: Adapter, connected_only: bool = True) -> list[Port]:
        with self._lock:
            self._ensure_open()
            result = []
            for position, handle in enumerate(self._display_handles(adapter)):
                properties = self._display_properties(handle)
                connected = bool(properties.DisplayConfigFlags & CTL_DISPLAY_ATTACHED)
                if connected_only and not connected:
                    continue
                if properties.Type != CTL_DISPLAY_OUTPUT_TYPES_DISPLAYPORT:
                    continue
                encoder = self._encoder_properties(handle)
                connector = (
                    ADL_CONNECTOR_EDP
                    if encoder.EncoderConfigFlags & CTL_ENCODER_INTERNAL_DISPLAY
                    else ADL_CONNECTOR_DISPLAY_PORT
                )
                windows_id = properties.Os_display_encoder_handle.WindowsDisplayEncoderID
                result.append(
                    Port(
                        adapter=adapter,
                        index=position,
                        logical_display_index=_handle_value(handle),
                        physical_display_index=windows_id,
                        name=f"Intel Display 0x{windows_id:08X}",
                        manufacturer="",
                        display_type=properties.Type,
                        output_type=encoder.Type,
                        connector=connector,
                        connected=connected,
                        backend="igcl",
                    )
                )
            return result

    @staticmethod
    def _validate_port(port: Port) -> None:
        if not port.connected:
            raise ValueError("port is not connected")

    def _aux(self, port: Port, operation: int, flags: int, address: int, data: bytes, length: int) -> bytes:
        self._validate_port(port)
        if not 0 < length <= CTL_AUX_MAX_DATA_SIZE:
            raise ValueError("AUX length must be in range 1..132")
        request = _CtlAuxAccessArgs()
        request.Size = ctypes.sizeof(request)
        request.OpType = operation
        request.Flags = flags
        request.Address = address
        request.DataSize = length
        if operation == CTL_OPERATION_TYPE_WRITE:
            request.Data[: len(data)] = data
        rc = -1
        for _ in range(RETRY_COUNT):
            rc = self._ctl.ctlAUXAccess(c_void_p(port.logical_display_index), byref(request))
            if rc == CTL_RESULT_SUCCESS:
                break
            time.sleep(0.01)
        self._check(rc, "Intel AUX transaction")
        if operation == CTL_OPERATION_TYPE_READ and request.DataSize < length:
            raise AuxError(f"Intel AUX read returned {request.DataSize} of {length} bytes")
        return bytes(request.Data[:length])

    def read_dpcd(self, port: Port, address: int, length: int) -> bytes:
        if length <= 0:
            raise ValueError("length must be positive")
        if not 0 <= address <= 0xFFFFF:
            raise ValueError("DPCD address must be in range 0x00000..0xFFFFF")
        with self._lock:
            self._ensure_open()
            output = bytearray()
            while len(output) < length:
                size = min(CTL_AUX_CHUNK_SIZE, length - len(output))
                output += self._aux(
                    port,
                    CTL_OPERATION_TYPE_READ,
                    CTL_AUX_FLAG_NATIVE_AUX,
                    address + len(output),
                    b"",
                    size,
                )
            return bytes(output)

    def write_dpcd(self, port: Port, address: int, data: bytes) -> None:
        data = bytes(data)
        if not data:
            raise ValueError("data must not be empty")
        if not 0 <= address <= 0xFFFFF:
            raise ValueError("DPCD address must be in range 0x00000..0xFFFFF")
        with self._lock:
            self._ensure_open()
            for offset in range(0, len(data), CTL_AUX_CHUNK_SIZE):
                chunk = data[offset : offset + CTL_AUX_CHUNK_SIZE]
                self._aux(
                    port,
                    CTL_OPERATION_TYPE_WRITE,
                    CTL_AUX_FLAG_NATIVE_AUX,
                    address + offset,
                    chunk,
                    len(chunk),
                )

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
            self._aux(
                port,
                CTL_OPERATION_TYPE_WRITE,
                CTL_AUX_FLAG_I2C_AUX_MOT,
                device_address,
                bytes((register,)),
                1,
            )
            output = bytearray()
            while len(output) < length:
                size = min(CTL_AUX_CHUNK_SIZE, length - len(output))
                final = len(output) + size >= length
                flags = CTL_AUX_FLAG_I2C_AUX if final else CTL_AUX_FLAG_I2C_AUX_MOT
                output += self._aux(port, CTL_OPERATION_TYPE_READ, flags, device_address, b"", size)
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
                self._aux(port, CTL_OPERATION_TYPE_WRITE, CTL_AUX_FLAG_I2C_AUX, device_address, data, len(data))
                return
            for offset in range(0, len(data), CTL_AUX_CHUNK_SIZE):
                chunk = data[offset : offset + CTL_AUX_CHUNK_SIZE]
                payload = bytes(((register + offset) & 0xFF,)) + chunk
                self._aux(
                    port,
                    CTL_OPERATION_TYPE_WRITE,
                    CTL_AUX_FLAG_I2C_AUX,
                    device_address,
                    payload,
                    len(payload),
                )
