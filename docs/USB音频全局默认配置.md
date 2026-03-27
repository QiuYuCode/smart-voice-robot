# USB 音频全局默认配置（C-Media 0d8c:0014）

适用目标：
- 所有用户默认使用 USB 声卡（C-Media `0d8c:0014`）
- 默认输出音量 `80%`
- 默认输入音量 `100%`

---

## 1) 先确认设备名（不要用 Bus/Device 编号）

`lsusb` 里的 `Bus 001 Device 008` 这类编号会变化，不能用于持久配置。  
应使用 PulseAudio/ALSA 的稳定设备名。

检查命令：

```bash
lsusb
pactl list short cards
pactl list short sinks
pactl list short sources
```

本机对应名称：
- Card: `alsa_card.usb-C-Media_Electronics_Inc._USB_Audio_Device-00`
- Sink(输出): `alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo`
- Source(输入): `alsa_input.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.mono-fallback`

---

## 2) PulseAudio 系统级默认（全用户）

创建系统级覆盖文件：

```bash
sudo mkdir -p /etc/pulse/default.pa.d

sudo tee /etc/pulse/default.pa.d/90-usb-audio-default.pa >/dev/null <<'EOF'
### Force USB C-Media as global default (all users)
set-default-sink alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo
set-default-source alsa_input.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.mono-fallback
set-sink-volume alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo 80%
set-source-volume alsa_input.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.mono-fallback 100%
EOF
```

说明：
- `/etc/pulse/default.pa` 默认会 `.include /etc/pulse/default.pa.d`，所以上面文件会对所有用户生效。
- `module-device-restore`/`module-default-device-restore` 会记忆用户历史设置；若用户手动改过，可能覆盖默认值。

---

## 3) ALSA 默认（给不走 PulseAudio 的程序）

很多 CLI 或底层程序直接走 ALSA，需要单独配置全局默认卡：

```bash
sudo cp /etc/asound.conf /etc/asound.conf.bak.$(date +%Y%m%d%H%M%S)

sudo tee /etc/asound.conf >/dev/null <<'EOF'
pcm.!default {
    type plug
    slave {
        pcm "hw:Device,0"
        channels 2
        rate 48000
    }
    hint.description "USB Audio Device (C-Media)"
}

ctl.!default {
    type hw
    card Device
}
EOF
```

---

## 4) 立即生效

```bash
pulseaudio -k || true
```

重新登录或重启后可确保所有用户会话都应用。

---

## 5) 验证

```bash
pactl info
pactl get-sink-volume alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo
pactl get-source-volume alsa_input.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.mono-fallback
aplay -l
arecord -l
```

预期：
- 默认输出：USB sink
- 默认输入：USB source
- 输出音量：`80%`
- 输入音量：`100%`

---

## 6) 常见故障与修复

### 故障 A：`pactl info` 显示 `auto_null`

表现：默认输出/输入变成空设备，系统无声。  
原因：通常是 ALSA 初始化失败（配置文件语法错误）导致 PulseAudio 退化到 null sink。

排查与修复：

```bash
aplay -l
arecord -l
```

若看到 `~/.asoundrc may be old or corrupted`，删除用户错误配置：

```bash
rm -f ~/.asoundrc
pulseaudio -k || true
```

### 故障 B：USB 名称不存在

表现：`set-default-sink` 报无此实体。  
原因：USB 未插好、枚举变化或设备暂未被检测。  
做法：重新插拔设备后，重新执行 `pactl list short sinks/sources` 获取实时名称。

