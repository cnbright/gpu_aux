# gpu_aux

Windows x64 纯 Python GPU AUX 包。Python 使用 `ctypes` 直接加载系统 AMD`atiadlxx.dll`、NVIDIA `nvapi64.dll` 或 Intel IGCL `ControlLib.dll`，不包含或依赖C/C++ 中间 DLL

实现了AUX DPCD读写、IIC OVER AUX读写，以方便eDP&DP面板调试；

完整接口说明见 [API.md](./API.md)。

## 安装

通过 PyPI 安装：

```powershell
python -m pip install gpu-aux
```

从本地源码目录安装：

```powershell
python -m pip install .
```

## 运行权限

AMD backend 通常可在普通用户权限下运行；NVIDIA 和 Intel backend 访问底层
NVAPI/IGCL AUX 接口时需要以管理员权限启动 Python、PowerShell、CMD 或调用本库的上层程序。

支持：

- 按 PCI 地址合并 ADL 重复项，枚举物理 AMD GPU 和每个已连接 DP/eDP 端口
- 枚举 NVIDIA 物理 GPU 和已连接 DP 端口
- 枚举 Intel IGCL GPU 和已连接 DP/eDP 端口
- AMD DPCD 读写：`ADL_Display_NativeAUXChannel_Access`
- AMD I2C-over-AUX 读写：`ADL_Display_DDCBlockAccess_Get`
- NVIDIA DPCD/I2C-over-AUX 读写：`NvAPI_Disp_DpAuxChannelControl`
- Intel DPCD/I2C-over-AUX 读写：`ctlAUXAccess`
- 以 backend、GPU index 和显示目标 ID 区分多个 DP/eDP 端口

公开 GPU API 参考：

- AMD ADL SDK：[AMD Display Library](https://gpuopen-librariesandsdks.github.io/adl/)；
  DDC/I2C 入口见 [I2C, DDC and EDID APIs](https://gpuopen-librariesandsdks.github.io/adl/group__I2CDDCEDIDAPI.html)。
- Intel IGCL：[Programming Guide](https://intel.github.io/drivers.gpu.control-library/prog.html)
  和 [Control API](https://intel.github.io/drivers.gpu.control-library/Control/api.html)。
- NVIDIA NVAPI：[NVAPI Reference Documentation](https://docs.nvidia.com/nvapi/documentation.html)。
  本项目使用的 DP AUX 入口不在公开 `nvapi.h` 中声明，属于逆向确认的私有接口。

公共 `AuxPort` API 对 AMD、NVIDIA 和 Intel 保持统一语义：`read_dpcd()` /
`i2c_read()` 的 `length` 是实际要读取的字节数，`write_dpcd()` /
`i2c_write()` 的 `data` 是实际要写出的完整 payload。NVIDIA 私有 NVAPI AUX
请求内部的 `length_field` 使用 `N - 1` 编码，这个差异由 `gpu_aux.nvapi`
backend 内部处理；上层调用方不要额外增减长度，也不要为 NVIDIA 拼接填充字节。

使用前应先枚举 GPU 与端口，确认要访问的显示器对应的 `backend`、`gpu_index`、`kind`
和端口 `index`。GPU 与端口枚举是两个独立的模块级函数，不需要先创建 `AuxPort`：

```python
from gpu_aux import enumerate_gpus, enumerate_ports

for gpu_index, gpu in enumerate(enumerate_gpus("NVIDIA")):
    print(gpu_index, gpu.backend, gpu.name)
    for port_index, port in enumerate(enumerate_ports("NVIDIA", gpu_index)):
        print(port_index, port.kind, port.identity, port.name)
```

`gpu_index` 来自 `enumerate_gpus()` 的枚举序号；`index` 来自同一 GPU、同一端口类型下的
端口枚举序号，不要直接使用 Windows 显示设置编号，也不要把 `identity` 中的底层显示 ID
当作 `index`。例如第二个外接 DP 使用 `AuxPort("DP", index=1, gpu_index=0, backend="NVIDIA")`。

确认参数后再构造端口对象：

```python
from gpu_aux import AuxPort

with AuxPort("DP", index=1, gpu_index=0, backend="NVIDIA") as dp:
    print(dp.read_dpcd(0x00000, 16).hex(" "))
    dp.i2c_write(0xA0, b"\x00")
    edid = dp.i2c_read(0xA0, 128)
```

多个同后端 `AuxPort`对象共享同一 context，并在最后一个对象关闭时释放。后端必须由调用方显式指定，不会自动选择。

## 测试

从项目根目录运行只读测试：

```powershell
python .\tests\smoke_test.py NVIDIA
python .\tests\smoke_test.py INTEL
```

读写硬件测试会向 DPCD `0x00102` 写入 `C0`、回读并恢复原值，同时通过
I2C write address `0x60/0xA0` 读取 EDID：

```powershell
python .\tests\hardware_aux_test_nvidia.py
```

AMD 写测试使用独立入口：

```powershell
python .\tests\hardware_aux_test_amd.py
```

Intel 写测试也使用独立入口：

```powershell
python .\tests\hardware_aux_test_intel.py
```

私有 ADL/NVAPI AUX 接口可能随显卡驱动变化；Intel 路径使用公开 IGCL
`ctlAUXAccess`。当前实现要求 Windows x64、64 位 Python、AMD/NVIDIA/Intel
DP/eDP 链路；包内会串行化 AUX 事务。
