# AGENTS.md

## 项目目标

本项目提供 Windows x64 下的纯 Python GPU AUX 访问能力。当前可运行 backend
为 AMD、NVIDIA 和 Intel，Python 通过 `ctypes` 直接加载系统
`atiadlxx.dll`/`atiadlxy.dll`、`nvapi64.dll` 或 Intel IGCL `ControlLib.dll`，实现：

- AMD/NVIDIA/Intel GPU 与 DP/eDP 端口枚举
- DPCD 读写
- I2C-over-AUX 读写
- 多 GPU、多 DP/eDP 端口的独立寻址

## 架构约束

- 保持纯 Python 实现，不新增 C/C++、Cython、Rust 或自建 DLL 中间层。
- 不链接、加载或调用 `OperateCardLib.dll`。它只能在用户明确要求时作为静态逆向样本。
- AMD 运行路径必须直接调用系统 ADL，NVIDIA 运行路径必须直接调用系统 NVAPI，
  Intel 运行路径必须直接调用系统 IGCL；三者都不复制或包装参考 DLL 的导出函数。
- 公共 API 位于 `gpu_aux` 包；底层 `ctypes` 结构和私有绑定集中在 backend 模块内。
- ADL、NVAPI 和 IGCL 是进程级接口，各 backend 的所有交易必须串行化，并保证初始化与
  销毁成对执行。
- 多个公开 `AuxPort` 对象必须按 backend 共享 context，通过引用计数管理释放。

## 当前代码

- `gpu_aux/adl.py`：AMD ADL 结构体、函数绑定、GPU/端口枚举及底层 AUX 操作。
- `gpu_aux/nvapi.py`：NVIDIA NVAPI 结构体、私有函数绑定、GPU/端口枚举及底层 AUX 操作。
- `gpu_aux/intel.py`：Intel IGCL 结构体、函数绑定、GPU/端口枚举及底层 AUX 操作。
- `gpu_aux/api.py`：`AuxPort` 端口对象、共享 backend context 和模块级设备枚举。
- `gpu_aux/__init__.py`：稳定的包级公开接口。
- `tests/smoke_test.py`：只读枚举和 DPCD 读取测试。
- `tests/hardware_aux_test_amd.py`：会写 AMD 硬件的 DPCD/I2C-over-AUX 测试。
- `tests/hardware_aux_test_nvidia.py`：会写 NVIDIA 硬件的 DPCD/I2C-over-AUX 测试。
- `tests/hardware_aux_test_intel.py`：会写 Intel 硬件的 DPCD/I2C-over-AUX 测试。
- `GPU_AUX_BACKEND_RESEARCH.md`：AMD、Intel、NVIDIA 底层 API 与逆向证据。

## 设备模型

- `Adapter` 表示物理 GPU。AMD ADL 可能按 `DISPLAYx` 返回同一 PCI 设备的多个
  逻辑 adapter，必须按 PCI bus/device/function 去重。
- `Port` 表示独立 DP/eDP 目标。AMD 身份由 ADL adapter index 和 display logical
  index 共同确定；NVIDIA 身份由 physical GPU index 和 display ID 共同确定；
  Intel 身份由 IGCL device index 和 display output handle/Windows encoder ID 共同确定。
- `AuxPort(kind, index, gpu_index, backend=...)` 是公开操作对象；`index` 按同一
  backend、同一 GPU 下的同类型端口分别计数。
- 不得把“第一个 connected display”复用于所有 Windows 显示路径。
- HDMI 不是 AUX 目标，不应作为可读 DPCD 的 DP/eDP 端口返回。
- 多个外接 DP 设备必须保留各自的 logical display index，不能按显示器名称去重。

## ctypes 与私有 API 规则

- 所有 `ctypes.Structure` 必须声明完整字段并用 `ctypes.sizeof` 断言已知大小。
- 为每个外部函数明确设置 `argtypes` 和 `restype`。
- 保持 x64 Python 检查；不要声称支持 Win32。
- DPCD 地址范围为 `0x00000..0xFFFFF`，AMD/NVIDIA/Intel Native AUX 单次最多 16 字节。
- I2C 公共参数使用 7-bit device address；兼容输入 8-bit address 时必须统一归一化。
- 私有函数的命令值、结构偏移或调用约定必须有反汇编、官方头文件或实机结果支撑。
- 不得因为 DLL 中出现某个函数名就声称它被实际调用；必须核对调用点。
- 逆向恢复的结构应标记为 recovered/private，不得描述为稳定的厂商 ABI。

## 硬件安全

- 默认只运行只读测试，不自动运行 `tests/hardware_aux_test_amd.py`、
  `tests/hardware_aux_test_nvidia.py` 或 `tests/hardware_aux_test_intel.py`。
- 任何 DPCD/I2C 写操作都需要用户明确要求或授权。
- 写测试必须先读取原值，在 `finally` 中恢复，并回读验证恢复结果。
- 不要对未知、一次性、训练控制或可能改变链路状态的 DPCD 寄存器做探索性写入。
- 当前受控 DPCD 测试使用 `0x00102 <- 0xC0`，结束时恢复原值。
- EDID segment pointer `0x30` 写入只用于选择 segment；EDID 数据从 `0x50` 读取。
- 单个端口失败时应报告 adapter、port identity、地址和底层错误码，不应继续盲写。

## 验证命令

使用本机 64 位 Python 3.9：

```powershell
$python = 'C:\Users\admin\AppData\Local\Programs\Python\Python39\python.exe'
& $python -m compileall gpu_aux tests
& $python .\tests\smoke_test.py AMD
& $python .\tests\smoke_test.py NVIDIA
& $python .\tests\smoke_test.py INTEL
& $python -m pip install --no-deps --force-reinstall .
```

仅在明确允许硬件写入后运行：

```powershell
& $python .\tests\hardware_aux_test_amd.py
& $python .\tests\hardware_aux_test_nvidia.py
& $python .\tests\hardware_aux_test_intel.py
```

完成修改后至少验证：

- 包可以导入且 wheel 构建/安装成功。
- AMD GPU 去重结果合理。
- NVIDIA GPU 与已连接 DP/eDP 端口枚举结果合理。
- Intel GPU 与已连接 DP/eDP 端口枚举结果合理。
- 每个已连接 DP/eDP 端口具有唯一 `Port.identity`。
- 每个端口分别读取 DPCD `0x00000..0x0000F`，不把一块面板结果复制给其他端口。
- I2C EDID 读取具有 `00 FF FF FF FF FF FF 00` 头且 128 字节 checksum 为零。

## 文档与提交要求

- 新增或修改私有 API 结论时同步更新 `GPU_AUX_BACKEND_RESEARCH.md`。
- 研究记录必须包含样本版本/hash、函数名或接口 ID、调用点、结构大小和置信度。
- README 只描述当前实际可运行功能；未实现 backend 不得列为已支持。
- 不提交 `build/`、`*.egg-info/`、`__pycache__/`、DLL、LIB、PDB 或临时反汇编文件。
- 保持 Python 3.9 兼容，默认使用 ASCII 代码标识符；文档可使用 UTF-8 中文。
