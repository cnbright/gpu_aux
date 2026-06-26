# gpu_aux API 说明

`gpu_aux` 是 Windows x64 下的纯 Python DisplayPort AUX 访问库。公共 API
集中从 `gpu_aux` 包导入，底层 AMD ADL、NVIDIA NVAPI、Intel IGCL 绑定属于实现细节。

## 导入

```python
from gpu_aux import (
    AuxError,
    AuxPort,
    enumerate_gpus,
    enumerate_gpus_and_ports,
    enumerate_ports,
)
```

支持的 `backend` 参数为：

| backend | 底层接口 | 运行依赖 |
| --- | --- | --- |
| `"AMD"` | AMD ADL | 系统可加载 `atiadlxx.dll` 或 `atiadlxy.dll` |
| `"NVIDIA"` | NVIDIA NVAPI | 系统可加载 `nvapi64.dll` |
| `"INTEL"` | Intel IGCL | 系统可加载 Intel IGCL `ControlLib.dll` |

`backend` 大小写不敏感，会在内部归一化为 `"AMD"`、`"NVIDIA"` 或 `"INTEL"`。

## 快速示例

枚举 GPU 和端口：

```python
from gpu_aux import enumerate_gpus, enumerate_ports

backend = "NVIDIA"

for gpu_index, gpu in enumerate(enumerate_gpus(backend)):
    print(gpu_index, gpu.backend, gpu.name, gpu.display_name)

    for port in enumerate_ports(backend, gpu_index):
        print(port.kind, port.identity, port.name)
```

读取第一个 NVIDIA DP 端口的 DPCD 头 16 字节：

```python
from gpu_aux import AuxPort

with AuxPort("DP", index=0, gpu_index=0, backend="NVIDIA") as port:
    data = port.read_dpcd(0x00000, 16)
    print(data.hex(" ").upper())
```

读取 EDID：

```python
from gpu_aux import AuxPort

with AuxPort("DP", index=0, gpu_index=0, backend="NVIDIA") as port:
    port.i2c_write(0xA0, b"\x00")
    edid = port.i2c_read(0xA0, 128)
    print(edid[:8].hex(" ").upper())
    print("checksum:", sum(edid) & 0xFF)
```

## 枚举 API

### `enumerate_gpus(backend: str) -> list[Adapter]`

返回指定 backend 下的物理 GPU 列表，不需要创建 `AuxPort`。

```python
from gpu_aux import enumerate_gpus

for gpu in enumerate_gpus("AMD"):
    print(gpu.index, gpu.name, gpu.bus, gpu.device, gpu.function)
```

AMD backend 会按 PCI bus/device/function 合并 ADL 可能返回的重复逻辑 adapter。

### `enumerate_ports(backend: str, gpu_index: int = 0) -> list[Port]`

返回指定 GPU 上已连接的 DP/eDP AUX 端口列表。

```python
from gpu_aux import enumerate_ports

for port in enumerate_ports("INTEL", gpu_index=0):
    print(port.kind, port.identity)
```

`gpu_index` 是 `enumerate_gpus(backend)` 返回列表中的序号。若索引不存在，
会抛出 `AuxError`。

### `enumerate_gpus_and_ports(backend: str) -> list[GpuPorts]`

一次返回 GPU 和端口快照。

```python
from gpu_aux import enumerate_gpus_and_ports

for item in enumerate_gpus_and_ports("NVIDIA"):
    print(item.gpu_index, item.adapter.name)
    for port in item.ports:
        print(" ", port.kind, port.identity)
```

返回项 `GpuPorts` 包含：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `gpu_index` | `int` | GPU 在该 backend 下的序号 |
| `adapter` | `Adapter` | GPU 信息 |
| `ports` | `tuple[Port, ...]` | 该 GPU 上的已连接 DP/eDP 端口快照 |

## `AuxPort`

```python
AuxPort(kind: str, index: int = 0, gpu_index: int = 0, *, backend: str)
```

打开一个 DP/eDP AUX 端点。推荐用 `with` 管理生命周期：

```python
from gpu_aux import AuxPort

with AuxPort("eDP", index=0, gpu_index=0, backend="AMD") as port:
    print(port.identity)
```

参数：

| 参数 | 说明 |
| --- | --- |
| `kind` | 端口类型，支持 `"DP"` 或 `"eDP"`，大小写不敏感 |
| `index` | 同一 GPU、同一 `kind` 下的端口序号，从 `0` 开始 |
| `gpu_index` | 同一 backend 下的 GPU 序号，从 `0` 开始 |
| `backend` | 必填关键字参数，支持 `"AMD"`、`"NVIDIA"`、`"INTEL"` |

例如，同一 NVIDIA GPU 上第二个外接 DP 端口：

```python
AuxPort("DP", index=1, gpu_index=0, backend="NVIDIA")
```

多个同 backend 的 `AuxPort` 会共享同一个底层 context，并通过引用计数在最后一个
对象关闭时释放。显式调用 `close()` 后，继续使用该对象会抛出 `AuxError`。

### 属性

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| `info` | `Port` | 当前端口信息 |
| `identity` | `str` | backend 内唯一端口标识 |
| `kind` | `str` | `"DP"` 或 `"eDP"` |
| `gpu_index` | `int` | GPU 序号 |
| `backend` | `str` | `"AMD"`、`"NVIDIA"` 或 `"INTEL"` |
| `index` | `int` | 同 GPU、同端口类型下的端口序号 |

## DPCD 方法

### `read_dpcd(address: int, length: int) -> bytes`

读取 DPCD 数据。`address` 范围为 `0x00000..0xFFFFF`，`length` 必须大于 `0`。
库会按底层接口限制自动分块，当前各 backend 单次 Native AUX 分块最大 16 字节。

```python
with AuxPort("DP", 0, 0, backend="NVIDIA") as port:
    dpcd = port.read_dpcd(0x00000, 16)
```

### `write_dpcd(address: int, data: bytes) -> None`

写入 DPCD 数据。`data` 不能为空。写操作会改变硬件状态，建议先读取原值，并在
`finally` 中恢复。

```python
with AuxPort("DP", 0, 0, backend="AMD") as port:
    address = 0x00102
    old = port.read_dpcd(address, 1)
    try:
        port.write_dpcd(address, bytes([0xC0]))
    finally:
        port.write_dpcd(address, old)
```

## I2C-over-AUX 方法

公共 I2C 参数使用 raw 8-bit write address，例如 EDID 数据地址 `0xA0`、EDID
segment pointer 地址 `0x60`。写入时不会自动插入 register/offset 字节，传入的
`data` 就是 I2C-over-AUX payload。

### `i2c_read(device: int, length: int) -> bytes`

从 I2C 设备当前内部指针读取数据。`device` 必须是偶数 write address byte，
范围为 `0x00..0xFE`，`length` 必须大于 `0`。如果设备需要先设置 offset，
请先调用 `i2c_write(device, data)` 写入 offset 字节。

```python
with AuxPort("DP", 0, 0, backend="INTEL") as port:
    port.i2c_write(0xA0, b"\x00")
    edid = port.i2c_read(0xA0, 128)
```

### `i2c_write(device: int, data: bytes) -> None`

向 I2C 设备写入 raw payload。`device` 必须是偶数 write address byte，`data`
不能为空。比如对 write address `0x4E` 只写入 `0x23`：

```python
with AuxPort("DP", 0, 0, backend="NVIDIA") as port:
    port.i2c_write(0x4E, b"\x23")
```

一次写入多个字节时，把完整 payload 放进同一个 `bytes`：

```python
with AuxPort("DP", 0, 0, backend="AMD") as port:
    port.i2c_write(0x4E, bytes([0x23, 0x45, 0x67]))
```

如果目标设备协议要求第一个字节是内部 offset/register，也由调用方显式放入
payload：

```python
with AuxPort("DP", 0, 0, backend="AMD") as port:
    port.i2c_write(0x4E, bytes([0x10, 0x23, 0x45, 0x67]))
```

## 数据类

### `Adapter`

`Adapter` 表示一个物理 GPU。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `index` | `int` | backend 内 GPU 序号或底层 adapter index |
| `name` | `str` | GPU 名称 |
| `display_name` | `str` | 显示名称 |
| `bus` | `int` | PCI bus |
| `device` | `int` | PCI device |
| `function` | `int` | PCI function |
| `backend` | `str` | `"AMD"`、`"NVIDIA"` 或 `"INTEL"` |

### `Port`

`Port` 表示一个已连接的 DP/eDP AUX 目标。

| 字段/属性 | 类型 | 说明 |
| --- | --- | --- |
| `adapter` | `Adapter` | 所属 GPU |
| `index` | `int` | backend 枚举结果中的端口位置 |
| `logical_display_index` | `int` | backend 用于访问该端口的逻辑 ID |
| `physical_display_index` | `int` | backend 暴露的物理/Windows 显示 ID |
| `name` | `str` | 显示目标名称 |
| `manufacturer` | `str` | 厂商名，部分 backend 可能为空 |
| `display_type` | `int` | backend 显示类型值 |
| `output_type` | `int` | backend 输出类型值 |
| `connector` | `int` | backend connector 值 |
| `connected` | `bool` | 是否连接 |
| `backend` | `str` | 底层 backend 标记，例如 `adl`、`nvapi`、`igcl` |
| `identity` | `str` | 端口身份字符串 |
| `kind` | `str` | `"DP"` 或 `"eDP"` |

`identity` 可用于日志和问题定位，但不要把它当成跨驱动版本永久稳定的硬件序列号。

## 异常

### `AuxError`

底层库加载、backend 初始化、GPU/端口不存在、AUX 交易失败等运行时错误会抛出
`AuxError`。

```python
from gpu_aux import AuxError, enumerate_gpus

try:
    print(enumerate_gpus("NVIDIA"))
except AuxError as error:
    print("NVIDIA backend unavailable:", error)
```

参数类型或范围错误通常抛出 `TypeError` 或 `ValueError`。

## 安全建议

- 默认优先使用 `enumerate_gpus()`、`enumerate_ports()` 和 `read_dpcd()` 做只读检查。
- 不要对未知 DPCD 地址做探索性写入。
- 写入前先读取原值，并在 `finally` 中恢复。
- 单个端口失败时记录 `backend`、`gpu_index`、`port.identity`、地址和错误信息。
- HDMI 不是 AUX 目标，本库只枚举 DP/eDP 端口。
