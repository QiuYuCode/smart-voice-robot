"""
RK3328 降噪板串口协议驱动

基于《RK3328 降噪板协议手册 V1.0》实现。
职责：串口通信、协议帧解析、握手响应、唤醒事件检测、主控消息发送。

协议要点：
  - 串口参数: 115200, 8N1, 无流控
  - 帧格式: 0xA5 | userID(0x01) | msgType | dataLen(2B LE) | msgID(2B LE) | data | checksum
  - 校验码: ~sum(除校验码外所有字节) + 1, 取低 8 位
  - 消息类型: 0x01=握手, 0x04=设备消息, 0x05=主控消息, 0xFF=确认
  - 握手: 模块通电后每 500ms 发一次, 主控需 50ms 内回复确认消息(同 msgID)
  - 唤醒事件: 设备消息, JSON 载荷 type="aiui_event", eventType=4
"""

from __future__ import annotations

import json
import queue
import struct
import threading
import time
from dataclasses import dataclass, field

import serial


# ---------------------------------------------------------------------------
# 协议常量
# ---------------------------------------------------------------------------

SYNC_BYTE = 0xA5
USER_ID = 0x01
HEADER_SIZE = 7  # sync(1) + userID(1) + msgType(1) + dataLen(2) + msgID(2)

# 消息类型
MSG_TYPE_HANDSHAKE = 0x01
MSG_TYPE_DEVICE = 0x04
MSG_TYPE_HOST = 0x05
MSG_TYPE_ACK = 0xFF

# 握手 / 确认消息的固定数据部分
ACK_DATA = bytes([0xA5, 0x00, 0x00, 0x00])


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class WakeEvent:
    """硬件唤醒事件"""
    keyword: str = ""       # 唤醒词 (拼音)
    beam: int = 0           # 唤醒波束号
    angle: float = 0.0      # 唤醒角度
    info: dict = field(default_factory=dict)   # 原始 info 字段
    timestamp: float = 0.0  # 事件时间戳


# ---------------------------------------------------------------------------
# 协议帧解析工具
# ---------------------------------------------------------------------------

def calc_checksum(data: bytes) -> int:
    """
    计算校验码：除校验码字节外所有字节求和取反并加 1，取低 8 位。

    checkcode = (~sum(byte_0 + byte_1 + ... + byte_n) + 1) & 0xFF
    """
    return (~sum(data) + 1) & 0xFF


def build_frame(msg_type: int, msg_id: int, payload: bytes) -> bytes:
    """
    构建完整的协议帧。

    Args:
        msg_type: 消息类型 (0x01/0x04/0x05/0xFF)
        msg_id: 消息 ID (0-65535, 循环使用)
        payload: 消息数据

    Returns:
        完整的帧字节串 (含同步头、校验码)
    """
    data_len = len(payload)
    # header: sync + userID + msgType + dataLen(2B LE) + msgID(2B LE)
    header = struct.pack(
        "<BBBHH",
        SYNC_BYTE,
        USER_ID,
        msg_type,
        data_len,
        msg_id,
    )
    frame_without_checksum = header + payload
    checksum = calc_checksum(frame_without_checksum)
    return frame_without_checksum + bytes([checksum])


# ---------------------------------------------------------------------------
# RK3328 驱动
# ---------------------------------------------------------------------------

class RK3328Driver:
    """
    RK3328 降噪板串口驱动。

    使用后台线程持续读取串口，自动处理握手，解析设备消息，
    将唤醒事件放入 wake_event_queue 供行为树节点消费。

    用法:
        driver = RK3328Driver("/dev/ttyUSB0")
        driver.start()
        ...
        event = driver.wake_event_queue.get(timeout=1)
        ...
        driver.stop()
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.05):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

        self._serial: serial.Serial | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()  # 保护串口写操作

        # 消息 ID 计数器 (0-65535 循环)
        self._msg_id_counter = 0

        # 唤醒事件队列 —— 供 HardwareWakeWord 节点消费
        self.wake_event_queue: queue.Queue[WakeEvent] = queue.Queue()

        # 握手状态
        self.handshake_ok = False

        # 接收缓冲区
        self._recv_buf = bytearray()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self):
        """打开串口并启动后台读取线程。"""
        if self._running:
            return
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
        )
        self._running = True
        self._thread = threading.Thread(
            target=self._read_loop, name="rk3328-reader", daemon=True
        )
        self._thread.start()
        print(f"[RK3328] 串口已打开: {self.port} @ {self.baudrate}")

    def stop(self):
        """停止后台线程并关闭串口。"""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
            self._serial = None
        print("[RK3328] 串口已关闭。")

    # ------------------------------------------------------------------
    # 主控消息发送
    # ------------------------------------------------------------------

    def _next_msg_id(self) -> int:
        """获取下一个消息 ID (0-65535 循环)。"""
        mid = self._msg_id_counter
        self._msg_id_counter = (self._msg_id_counter + 1) & 0xFFFF
        return mid

    def send_command(self, payload: dict) -> None:
        """
        发送主控消息 (msgType=0x05)。

        Args:
            payload: JSON 可序列化的字典，如:
                {"type": "manual_wakeup", "content": {"beam": 1}}
        """
        json_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        frame = build_frame(MSG_TYPE_HOST, self._next_msg_id(), json_bytes)
        self._write(frame)

    def send_switch_mic(self, mic_type: str = "mic6_circle") -> None:
        """发送麦克风阵列切换指令。"""
        self.send_command({
            "type": "switch_mic",
            "content": {"mic": mic_type},
        })

    def send_manual_wakeup(self, beam: int = 1) -> None:
        """发送手动唤醒指令。"""
        self.send_command({
            "type": "manual_wakeup",
            "content": {"beam": beam},
        })

    def send_wakeup_keywords(self, keyword: str, threshold: str = "900") -> None:
        """发送唤醒词更换指令 (浅定制)。"""
        self.send_command({
            "type": "wakeup_keywords",
            "content": {"keyword": keyword, "threshold": threshold},
        })

    def send_get_version(self) -> None:
        """发送获取版本信息指令。"""
        self.send_command({"type": "verison"})  # 协议原文拼写

    # ------------------------------------------------------------------
    # 队列管理
    # ------------------------------------------------------------------

    def clear_wake_events(self) -> None:
        """清空所有待处理的唤醒事件。"""
        while not self.wake_event_queue.empty():
            try:
                self.wake_event_queue.get_nowait()
            except queue.Empty:
                break

    # ------------------------------------------------------------------
    # 内部：串口读写
    # ------------------------------------------------------------------

    def _write(self, data: bytes) -> None:
        """线程安全地写入串口。"""
        with self._lock:
            if self._serial is not None and self._serial.is_open:
                self._serial.write(data)

    def _send_ack(self, msg_id: int) -> None:
        """发送确认消息 (msgType=0xFF)，使用与被确认消息相同的 msgID。"""
        frame = build_frame(MSG_TYPE_ACK, msg_id, ACK_DATA)
        self._write(frame)

    # ------------------------------------------------------------------
    # 内部：后台读取线程
    # ------------------------------------------------------------------

    def _read_loop(self) -> None:
        """后台线程主循环：持续读取串口字节流，解析协议帧。"""
        while self._running:
            try:
                if self._serial is None or not self._serial.is_open:
                    time.sleep(0.1)
                    continue

                # 批量读取可用字节
                available = self._serial.in_waiting
                if available > 0:
                    chunk = self._serial.read(available)
                    self._recv_buf.extend(chunk)
                else:
                    # 无数据时短暂读取（受 timeout 控制）避免忙等
                    chunk = self._serial.read(1)
                    if chunk:
                        self._recv_buf.extend(chunk)

                # 尝试从缓冲区解析完整帧
                self._try_parse_frames()

            except serial.SerialException as e:
                print(f"[RK3328] 串口异常: {e}")
                time.sleep(1.0)
            except Exception as e:
                print(f"[RK3328] 读取线程异常: {e}")
                time.sleep(0.1)

    def _try_parse_frames(self) -> None:
        """尝试从接收缓冲区中解析所有完整的协议帧。"""
        while True:
            # 寻找同步头
            sync_pos = self._find_sync()
            if sync_pos < 0:
                # 没有同步头，清空缓冲区
                self._recv_buf.clear()
                return
            if sync_pos > 0:
                # 丢弃同步头之前的垃圾字节
                del self._recv_buf[:sync_pos]

            # 检查是否有足够字节读取头部
            if len(self._recv_buf) < HEADER_SIZE:
                return

            # 解析数据长度 (小端)
            data_len = struct.unpack_from("<H", self._recv_buf, 3)[0]
            frame_len = HEADER_SIZE + data_len + 1  # +1 校验码

            # 检查是否有完整帧
            if len(self._recv_buf) < frame_len:
                return

            # 提取帧
            frame = bytes(self._recv_buf[:frame_len])
            del self._recv_buf[:frame_len]

            # 校验
            expected_checksum = frame[-1]
            actual_checksum = calc_checksum(frame[:-1])
            if expected_checksum != actual_checksum:
                print(
                    f"[RK3328] 校验码错误: 期望 0x{expected_checksum:02X}, "
                    f"实际 0x{actual_checksum:02X}, 丢弃帧"
                )
                continue

            # 解析帧头字段
            msg_type = frame[2]
            msg_id = struct.unpack_from("<H", frame, 5)[0]
            payload = frame[HEADER_SIZE:-1]

            # 分发处理
            self._dispatch(msg_type, msg_id, payload)

    def _find_sync(self) -> int:
        """在接收缓冲区中查找同步头 0xA5 的位置。"""
        try:
            return self._recv_buf.index(SYNC_BYTE)
        except ValueError:
            return -1

    def _dispatch(self, msg_type: int, msg_id: int, payload: bytes) -> None:
        """根据消息类型分发处理。"""
        if msg_type == MSG_TYPE_HANDSHAKE:
            self._handle_handshake(msg_id)
        elif msg_type == MSG_TYPE_DEVICE:
            self._handle_device_message(msg_id, payload)
        elif msg_type == MSG_TYPE_ACK:
            # 收到确认消息（通常是对我们发出的主控消息的确认）
            pass
        else:
            print(f"[RK3328] 未知消息类型: 0x{msg_type:02X}")

    def _handle_handshake(self, msg_id: int) -> None:
        """处理握手请求：立即回复确认消息。"""
        self._send_ack(msg_id)
        if not self.handshake_ok:
            self.handshake_ok = True
            print("[RK3328] 握手成功，串口通信正常。")

    @staticmethod
    def _ensure_dict(value) -> dict:
        """确保值为 dict；若为 JSON 字符串则自动解析，否则返回空 dict。"""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
        return {}

    def _handle_device_message(self, msg_id: int, payload: bytes) -> None:
        """处理设备消息：解析 JSON，识别唤醒事件。"""
        # 回复确认
        self._send_ack(msg_id)

        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"[RK3328] 设备消息 JSON 解析失败: {e}")
            return

        msg_type_str = data.get("type", "")
        # content / info 可能是 dict，也可能是嵌套的 JSON 字符串
        content = self._ensure_dict(data.get("content", {}))

        if msg_type_str == "aiui_event":
            event_type = content.get("eventType")
            if event_type == 4:
                # 唤醒事件
                info = self._ensure_dict(content.get("info", {}))
                info_ivw = info.get("ivw", "")
                wake_word = info_ivw.get("keyword", "")
                event = WakeEvent(
                    keyword=wake_word,
                    beam=content.get("arg1", 0),
                    angle=info_ivw.get("angle", 0.0),
                    info=info,
                    timestamp=time.time(),
                )
                self.wake_event_queue.put(event)
                print(
                    f"[RK3328] 唤醒事件: keyword={event.keyword}, "
                    f"beam={event.beam}, angle={event.angle}"
                )
            else:
                print(f"[RK3328] AIUI 事件: eventType={event_type}")
        else:
            print(f"[RK3328] 设备消息: type={msg_type_str}")
