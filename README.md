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

## 安装

```bash
cd /home/xyq/modbus-force-reader
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
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

持续读取（默认每 100 ms 一次，按 `Ctrl+C` 停止）：

```bash
modbus-force-reader --port /dev/ttyUSB0
```

示例输出：

```text
Reading /dev/ttyUSB0: slave=1, baud=9600, format=8N1, channel=1, register=80 (0x0050)
2026-09-29T14:30:00.123+08:00 force_raw=132 registers=[0x0000, 0x0084]
```

如果设备已按 `0.001 N/计数` 标定，可仅对显示值应用倍率和单位：

```bash
modbus-force-reader --port /dev/ttyUSB0 --scale 0.001 --unit N
```

`--scale` 和 `--unit` 只改变终端显示，不会修改传感器配置。实际物理单位和小数位必须以
当前设备的标定设置为准；不确定时保留默认的 `raw` 输出。

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
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
```
