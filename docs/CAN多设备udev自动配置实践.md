# CAN 多设备 udev 自动配置实践（基础版）

## 目标

在机器人启动或设备热插拔时，自动完成以下动作：

- 将 3 个同型号 USB-CAN 设备固定命名为：
  - `can_chassis`
  - `can_left`
  - `can_right`
- 自动拉起接口并设置波特率：
  - `can_chassis` -> `500000`
  - `can_left` -> `1000000`
  - `can_right` -> `1000000`

适配器型号示例：`1d50:606f`（candleLight / gs_usb）。

---

## 结论先行

同型号 USB-CAN 设备可以稳定区分，关键不是看 `lsusb`，而是看每个网卡在 udev 下的唯一属性：

- `ID_SERIAL_SHORT`（优先）
- `ID_PATH`（备选）

本机实测 3 个设备有不同的 `ID_SERIAL_SHORT`，可直接按 serial 绑定。

---

## 1. 识别设备唯一标识

先确认当前接口对应关系（示例）：

- `can0`：底盘
- `can2`：右手
- `can3`：左手

读取属性：

```bash
udevadm info -q property -p /sys/class/net/can0
udevadm info -q property -p /sys/class/net/can2
udevadm info -q property -p /sys/class/net/can3
```

输出如下

```bash
DEVPATH=/devices/platform/bus@0/3610000.usb/usb1/1-2/1-2.2/1-2.2:1.0/net/can0
INTERFACE=can0
IFINDEX=10
SUBSYSTEM=net
USEC_INITIALIZED=589024944
ID_MM_CANDIDATE=1
ID_VENDOR=bytewerk
ID_VENDOR_ENC=bytewerk
ID_VENDOR_ID=1d50
ID_MODEL=candleLight_USB_to_CAN_adapter
ID_MODEL_ENC=candleLight\x20USB\x20to\x20CAN\x20adapter
ID_MODEL_ID=606f
ID_REVISION=0000
ID_SERIAL=bytewerk_candleLight_USB_to_CAN_adapter_0032004B5246571520393733
ID_SERIAL_SHORT=0032004B5246571520393733
ID_TYPE=generic
ID_BUS=usb
ID_USB_INTERFACES=:ffffff:fe0101:
ID_USB_INTERFACE_NUM=00
ID_USB_DRIVER=gs_usb
ID_VENDOR_FROM_DATABASE=OpenMoko, Inc.
ID_MODEL_FROM_DATABASE=Geschwister Schneider CAN adapter
ID_PATH=platform-3610000.usb-usb-0:2.2:1.0
ID_PATH_TAG=platform-3610000_usb-usb-0_2_2_1_0
ID_NET_DRIVER=gs_usb
ID_NET_LINK_FILE=/usr/lib/systemd/network/73-usb-net-by-mac.link
ID_NET_NAME=can0
SYSTEMD_ALIAS=/sys/subsystem/net/devices/can0
TAGS=:systemd:
CURRENT_TAGS=:systemd:
```

提取 `ID_SERIAL_SHORT` 后形成映射（示例）：

- `0032004B5246571520393733` -> `can_chassis`
- `0039001E4759530920353131` -> `can_right`
- `004400494759530920353131` -> `can_left`

---

## 2. 创建拉起脚本

文件：`/usr/local/sbin/can-link-up.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
IFACE="${1:?missing interface}"
BITRATE="${2:?missing bitrate}"
IP_BIN="$(command -v ip)"

# udev 时序下接口可能刚创建，短重试提高成功率
for _ in {1..15}; do
  if "$IP_BIN" link show "$IFACE" >/dev/null 2>&1; then
    "$IP_BIN" link set "$IFACE" down 2>/dev/null || true
    "$IP_BIN" link set "$IFACE" up type can bitrate "$BITRATE"
    exit 0
  fi
  sleep 0.2
done
exit 1
```

赋权：

```bash
sudo chmod +x /usr/local/sbin/can-link-up.sh
```

---

## 3. 配置 udev 规则（正确写法）

文件：`/etc/udev/rules.d/80-can-names.rules`

```bash
ACTION=="add", SUBSYSTEM=="net", KERNEL=="can*", ENV{ID_SERIAL_SHORT}=="0032004B5246571520393733", NAME="can_chassis", RUN+="/usr/local/sbin/can-link-up.sh can_chassis 500000"
ACTION=="add", SUBSYSTEM=="net", KERNEL=="can*", ENV{ID_SERIAL_SHORT}=="0039001E4759530920353131", NAME="can_right",   RUN+="/usr/local/sbin/can-link-up.sh can_right 1000000"
ACTION=="add", SUBSYSTEM=="net", KERNEL=="can*", ENV{ID_SERIAL_SHORT}=="004400494759530920353131", NAME="can_left",    RUN+="/usr/local/sbin/can-link-up.sh can_left 1000000"
```

重载并触发：

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=net --action=add
```

---

## 4. 验证

```bash
ip -details link show can_chassis
ip -details link show can_left
ip -details link show can_right
```

应看到：

- `state UP`
- `can_chassis` 为 `bitrate 500000`
- `can_left/can_right` 为 `bitrate 1000000`

---

## 5. 本次踩坑记录（重点）

### 现象

- 命名成功（`can_chassis/can_left/can_right` 已出现）
- 但接口仍 `DOWN`，`restart-ms 0`

### 根因

规则曾写成两段：

- 第一段：`NAME="can_chassis"`（命名）
- 第二段：`KERNEL=="can_chassis", RUN+=...`（拉起）

在 `add` 事件触发时，内核名仍是 `can0/can2/can3`，导致第二段 `KERNEL=="can_chassis"` 不匹配，`RUN` 不执行。

### 修复原则

将 `NAME=...` 与 `RUN+=...` 放在同一条按 `ID_SERIAL_SHORT` 匹配的规则中，保证同一次事件内完成命名与拉起。

---

## 6. 常用排查命令

查看 udev 属性：

```bash
udevadm info -q property -p /sys/class/net/can_chassis
```

手工验证脚本：

```bash
sudo /usr/local/sbin/can-link-up.sh can_chassis 500000
sudo /usr/local/sbin/can-link-up.sh can_left 1000000
sudo /usr/local/sbin/can-link-up.sh can_right 1000000
```

查看 udev 日志：

```bash
sudo journalctl -b -u systemd-udevd | rg "can-link-up|can_chassis|can_left|can_right|Failed|error"
```

---

## 7. 后续可选增强（暂不启用）

如果基础版稳定后再增强，可考虑：

- 在 `ip link set ... up` 增加 `restart-ms 100`（bus-off 自动恢复）
- 切换到 `udev + systemd template service`，提升可观测性和失败重试能力

当前建议：先做重启与热插拔回归测试，确认基础版长期稳定再升级。
