# amd_aux

Windows x64 纯 Python AMD AUX 包。Python 使用 `ctypes` 直接加载系统 AMD
`atiadlxx.dll`，不包含或依赖 C/C++ 中间 DLL，也不依赖 `OperateCardLib.dll`。

支持：

- 按 PCI 地址合并 ADL 重复项，枚举物理 AMD GPU 和每个已连接 DP/eDP 端口
- DPCD 读写：`ADL_Display_NativeAUXChannel_Access`
- I2C-over-AUX 读写：`ADL_Display_DDCBlockAccess_Get`
- 以 `ADL adapter index + display logical index` 区分 eDP 和多个外接 DP 端口

直接构造一个端口对象：

```python
from amd_aux import AuxPort

with AuxPort("eDP", index=0, gpu_index=0) as edp:
    print(edp.read_dpcd(0x00000, 16).hex(" "))
    edid = edp.i2c_read(0x50, 0, 128)
```

使用模块级函数列出全部 GPU 和端口：

```python
from amd_aux import enumerate_gpus_and_ports

for gpu in enumerate_gpus_and_ports():
    print(gpu.gpu_index, gpu.adapter.name)
    for port in gpu.ports:
        print(port.kind, port.identity, port.name)
```

`index` 是同一 GPU、同一端口类型内的序号，例如第二个外接 DP 使用
`AuxPort("DP", index=1, gpu_index=0)`。多个 `AuxPort` 对象共享进程级 ADL
context，并在最后一个对象关闭时释放。

## 测试

从项目根目录运行只读测试：

```powershell
C:\Users\admin\AppData\Local\Programs\Python\Python39\python.exe .\tests\smoke_test.py
```

读写硬件测试会向 DPCD `0x00102` 写入 `C0`、回读并恢复原值，同时通过
I2C 地址 `0x30/0x50` 读取 EDID：

```powershell
C:\Users\admin\AppData\Local\Programs\Python\Python39\python.exe .\tests\hardware_aux_test.py
```

私有 ADL API 可能随 AMD 驱动变化。当前实现要求 Windows x64、64 位 Python、
AMD DP/eDP 链路；ADL 是进程级全局接口，包内会串行化 AUX 事务。
