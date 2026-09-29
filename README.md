# Modbus Force Reader

通过 USB 转 RS485 接口读取力传感器的 Modbus RTU 寄存器，并在终端持续打印力值。
程序的通信路径是只读的，只使用 `0x03` 功能码，不会修改标定参数、清零或写入设备。

## 协议默认值

本项目依据随设备提供的《Modbus RTU 协议 (V3.80)》和《Modbus RTU 指令解析》实现：

- 从站地址：`1`
- 串口：`9600 8N1`
- 毛重（实时力值）：寄存器偏移 `80`，即文档中的 `40081` 和 `40082`
- 数据：高字在前的有符号 32 位补码整数
- 单通道默认请求：`01 03 00 50 00 02 C4 1A`

地址参数采用 Modbus 报文中的零基偏移，不要把 `40081` 直接传给 `--register`；对应参数是
`--register 80` 或 `--register 0x50`。

## 接线

1. 传感器/变送器的 `A`（或 `D+`）连接 USB-RS485 的 `A`（或 `D+`）。
2. `B`（或 `D-`）连接 `B`（或 `D-`）。
3. 建议连接信号地 `GND`；传感器供电按其铭牌和说明书单独连接。
4. 如果一直超时，可在断电后尝试对调 `A/B`，不同厂商的标记习惯可能相反。

不要把传感器电源正极接到 USB-RS485 的信号端。

## 安装（mamba / conda）

使用独立环境 `modbus-force-reader`。在项目目录执行：

```bash
cd /home/xyq/modbus-force-reader
mamba env create -f environment.yml
conda activate modbus-force-reader
python -m pip install --no-build-isolation --no-deps -e .
```

如果只安装了 conda，将 `mamba env create` 替换为 `conda env create` 即可。
依赖由环境文件安装，最后一步把本项目及命令行入口安装到该环境。
后续打开终端时先执行 `conda activate modbus-force-reader`。

无需激活环境也可以运行：

```bash
mamba run -n modbus-force-reader modbus-force-reader --port /dev/ttyUSB0
```

已有环境更新配置后，在项目目录执行：

```bash
mamba env update -n modbus-force-reader -f environment.yml
mamba run -n modbus-force-reader python -m pip install --no-build-isolation --no-deps -e .
```

列出串口，确认 USB-RS485 对应的设备名：

```bash
modbus-force-reader --list-ports
```

程序要求明确传入串口，不会自动选择或打开检测到的设备。

## 使用

读取一次：

```bash
modbus-force-reader --port /dev/ttyUSB0 --once --show-frames
```

持续读取（默认每次读取后等待 100 ms，按 `Ctrl+C` 停止）：

```bash
modbus-force-reader --port /dev/ttyUSB0
```

默认读取设备状态寄存器偏移 `8` 的小数位和偏移 `104` 的单位，
将毛重转换为 **N（牛顿）**。终端同一行刷新当前力及本次运行的绝对值峰值，
重定向输出或 `--show-frames` 时逐行输出。启动后不要同时修改设备标定或单位；修改后重启程序。

例如当前设备单位为 N、小数位为 1，寄存器值 `146` 对应 `14.6 N`。
示例输出：

```text
Reading /dev/ttyUSB0: slave=1, baud=9600, format=8N1, channel=1, register=80 (0x0050)
当前力: +13.2000 N  |  峰值(绝对值): 13.2000 N
```

如果设备已按 `0.001 N/计数` 标定，可仅对显示值应用倍率和单位：

```bash
modbus-force-reader --port /dev/ttyUSB0 --scale 0.001 --unit N
```

`--scale` 和 `--unit` 只改变终端显示，不会修改传感器配置。实际物理单位和小数位必须以
当前设备的标定设置为准。手动换算必须同时提供 `--scale` 和 `--unit`，优先于自动换算。
自动模式遇到未设置或未知单位时会提示错误，不会猜测单位。
若设备单位是 g、kg 或 t，使用标准重力 `9.80665 m/s²` 换算等效力。
显示小数位不代表测量精度；实际准确性取决于设备标定。

查看原始值：`modbus-force-reader --port /dev/ttyUSB0 --raw`。
自定义寄存器须使用手动换算或 `--raw`，避免套用毛重的单位设置。

多通道设备可用 `--channel`。程序按协议公式
`80 + 500 × (通道号 - 1)` 计算每个通道的毛重寄存器：

```bash
modbus-force-reader --port /dev/ttyUSB0 --channel 6
```

常用参数：

```text
--slave-id 1                 Modbus 从站地址，范围 1..247
--baudrate 9600              波特率
--parity N                   校验：N、E 或 O
--stopbits 1                 停止位：1 或 2
--register 80                通道 1 的零基寄存器偏移
--channel 1                  通道号，范围 1..8
--word-order high-low        32 位数据字序
--interval 0.1               轮询周期（秒）
--timeout 0.5                串口超时（秒）
--once                       只读一次
--raw                        显示原始计数，跳过单位查询
--show-frames                打印十六进制收发帧
```

## 常见问题

- `Permission denied`：将当前用户加入 `dialout` 组后重新登录，例如
  `sudo usermod -aG dialout "$USER"`。
- `serial timeout`：检查设备名、供电、A/B 接线、从站地址、波特率和校验方式。
- `CRC mismatch`：通常是串口参数不一致、线路干扰或读取了错误设备。
- 数值数量级不对：核对设备标定、小数位和重量单位，再设置 `--scale` 与 `--unit`。
- 数值高低字颠倒：尝试 `--word-order low-high`。

## 开发验证

无需连接硬件即可运行协议与串口模拟测试：

```bash
mamba run -n modbus-force-reader python -B -m unittest discover -s tests -v
```
