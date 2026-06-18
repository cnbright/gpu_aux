# GPU AUX Backend Reverse-Engineering Notes

## Scope and sample

This document records static reverse-engineering results for the reference
`OperateCardLib.dll`. The reference DLL is research input only and is not a
runtime dependency of this project.

- Sample: `C:\sorce\code\auto_test\OperateCardLib.dll`
- Architecture: Windows x64
- File version: `1.0.0.5`
- SHA-256: `1E5CCE27E02DEA4B7718EE438041D4A2478B9C8B61BF7E4ABA9446494C5F1EBC`
- Image base: `0x180000000`

Important exported RVAs in this sample:

| Export | RVA |
| --- | ---: |
| `NVCardInitial` | `0x3DDA0` |
| `IntelCardInitial_EDP` | `0x3E0A0` |
| `IntelCardInitial_DP` | `0x3E570` |
| `WriteDPCD_NV` | `0x3ECB0` |
| `ReadDPCD_NV` | `0x3EE30` |
| `WriteDPCD_INTEL` | `0x3EFB0` |
| `ReadDPCD_INTEL` | `0x3F1F0` |
| `IICRead` dispatcher | `0x43750` |
| `IICWrite` dispatcher | `0x437D0` |

## Confirmed backend map

| Platform | Loaded library/API | DPCD read/write | I2C-over-AUX read/write |
| --- | --- | --- | --- |
| AMD | `atiadlxx.dll` / `atiadlxy.dll` | `ADL_Display_NativeAUXChannel_Access` | `ADL_Display_DDCBlockAccess_Get` |
| Intel | Intel Graphics Control Library (`ControlLib.dll`) | `ctlAUXAccess`, or the `IDPControl2` read/write methods described below | `ctlAUXAccess`, or the same `IDPControl2` methods; not `ctlI2CAccess` in the observed call chain |
| NVIDIA | `nvapi64.dll`, function obtained through `nvapi_QueryInterface` | `NvAPI_Disp_DpAuxChannelControl` | `NvAPI_Disp_DpAuxChannelControl` |

The generic `ReadDPCD`, `WriteDPCD`, `IICRead`, and `IICWrite` exports dispatch
through a card-type byte. The relevant I2C jump-table entries confirm these
internal implementations:

| Backend | I2C write RVA | I2C read RVA |
| --- | ---: | ---: |
| Intel eDP/DP | `0x403E0` | `0x406F0` |
| NVIDIA | `0x3FFB0` | `0x401B0` |

## Intel implementation

### Initialization and resolved APIs

The binary contains the Intel Graphics Control Library loader and resolves at
least the following symbols:

- `ctlInit`, `ctlClose`
- `ctlEnumerateDevices`, `ctlEnumerateDisplayOutputs`
- `ctlGetDeviceProperties`, `ctlGetDisplayProperties`
- `ctlAUXAccess`, `ctlI2CAccess`

There are two Intel transaction paths selected by internal state:

1. A direct `ctlAUXAccess(display_output_handle, request)` path using a
   `0xB0`-byte request.
2. An object interface path created through `Create_DPControlLibrary2`. Its
   request is `0x94` bytes; read and write are virtual calls at vtable offsets
   `+0x158` and `+0x160` respectively.

The first path is positively identified because the wrapper at RVA `0x3BF10`
performs `GetProcAddress(..., "ctlAUXAccess")` and tail-calls the result with
the display handle and request pointer.

`ctlI2CAccess` is resolved by the loader, but no call from the observed Intel
DPCD or I2C-over-AUX implementations reaches it. Both I2C error strings also
explicitly identify `ctlAUXAccess`. Therefore, recording `ctlI2CAccess` as the
reference DLL's actual I2C backend would be incorrect.

### Direct `ctlAUXAccess` request

The following field layout is reconstructed from writes to the `0xB0` stack
object. Names are descriptive because the private structure definition is not
present in the sample.

```c
typedef struct IntelAuxRequest_Recovered {
    uint32_t size;          // +0x00 = 0xB0
    uint32_t reserved04;    // +0x04
    uint32_t operation;     // +0x08: 1 read, 2 write
    uint32_t access_type;   // +0x0C: 1 native AUX, 2/4 I2C phases
    uint32_t address;       // +0x10: DPCD address or shifted I2C address
    uint8_t  reserved14[16];
    uint32_t data_size;     // +0x24
    uint8_t  data[0x88];    // +0x28
} IntelAuxRequest_Recovered;
```

DPCD operation mapping:

- Read: `operation=1`, `access_type=1`, DPCD address at `+0x10`.
- Write: `operation=2`, `access_type=1`, DPCD address at `+0x10`.
- The public wrapper limits each DPCD transaction to 16 bytes.

I2C-over-AUX operation mapping:

- Write: `operation=2`, `access_type=2`, address is `dev7 << 1`; data begins
  with the register offset followed by payload. Payload chunks are at most 8
  bytes in this path.
- Read offset phase: `operation=2`, `access_type=4`, address is `dev7 << 1`,
  one register-offset byte is sent.
- Read data phase: `operation=1`, `access_type=2`, address is `dev7 << 1`, and
  returned bytes are taken from `data`. Read chunks are at most 16 bytes.

### `IDPControl2` request path

The alternate path uses a `0x94`-byte request passed to object methods rather
than directly calling an exported `ctl*` symbol. Recovered command values are:

| Operation | Command at `+0x04` |
| --- | ---: |
| DPCD write | `8` |
| DPCD read | `9` |
| I2C write | `0` |
| I2C read offset/data phases | `0`, then `1` or `5` |

The object method at vtable `+0x158` is used by read operations; `+0x160` is
used by write operations. The sample exposes factory names
`Create_DPControlLibrary`, `Create_DPControlLibrary2`, and corresponding
destroy functions. The exact public SDK type name and complete field semantics
cannot be proven from this binary alone, so these offsets must not be treated
as a stable ABI.

## NVIDIA implementation

### Resolved API

`NVCardInitial` loads `nvapi64.dll`, resolves `nvapi_QueryInterface`, and
obtains the function used by all four operations. Error paths identify it as:

```c
NvAPI_Disp_DpAuxChannelControl(displayId, request, 0x68)
```

No separate NVIDIA I2C API is used by the reference DLL. Native DPCD and
I2C-over-AUX are encoded in the same `0x68` request.

### Recovered request

```c
typedef struct NvDpAuxRequest_Recovered {
    uint32_t version;       // +0x00 = 0x00010028
    uint32_t display_id;    // +0x04
    uint32_t command;       // +0x08
    uint32_t address;       // +0x0C: DPCD address or I2C device address
    uint8_t  data[16];      // +0x10
    uint32_t length_field;  // +0x20, usually count - 1 for reads/DPCD
    uint32_t result;        // +0x24: 0 success, 1 defer, 2 not found, 0xFF timeout
    uint8_t  reserved[0x40];
} NvDpAuxRequest_Recovered;
```

Confirmed command mapping:

| Command | Meaning in reference DLL |
| ---: | --- |
| `0` | Native AUX DPCD write |
| `1` | Native AUX DPCD read |
| `2` | I2C-over-AUX write |
| `5` | I2C-over-AUX register-offset/write phase before a read |
| `6` | I2C-over-AUX read with continuation/MOT |
| `3` | Final I2C-over-AUX read phase |

DPCD is limited to 16 bytes per request. For I2C reads the implementation
sends command `5` with the register offset, then reads in chunks of at most 16
bytes using command `6` for intermediate chunks and command `3` for the final
chunk. I2C writes use command `2`, placing the register offset before payload
in `data`.

The error/result handling is also explicit in the disassembly:

- NVAPI return value nonzero: API call failure.
- `result == 0`: success.
- `result == 1`: defer.
- `result == 2`: requested data not found.
- `result == 0xFF`: timeout.

## Confidence and limitations

High-confidence findings are function identity, dispatch targets, request
sizes, command values, field offsets written by the reference DLL, and chunk
sizes. These come directly from x64 disassembly of the hashed sample.

The reconstructed C structures are documentation aids, not vendor headers.
Reserved fields, official enum names, and the complete `IDPControl2` ABI remain
unconfirmed. The NVIDIA function is private NVAPI and obtained by interface ID;
the numeric QueryInterface ID still needs separate recovery before a standalone
NVIDIA implementation can resolve it without an NVAPI header/library.

## Project dependency boundary

The current `amd_aux` Python package directly loads the system AMD ADL DLL via
`ctypes`. It does not load, import, redistribute, or call `OperateCardLib.dll`.
The Intel and NVIDIA information above is retained only as implementation
research for future direct Python backends.
