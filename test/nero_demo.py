import json
import subprocess
import threading
import time
from pathlib import Path
from pyAgxArm import AgxArmFactory, create_agx_arm_config, NeroFW


def wait_motion_done(arm, timeout: float = 10.0, poll_interval: float = 0.1) -> bool:
    """等待机械臂运动完成（motion_status == 0）。"""
    time.sleep(0.5)
    start_t = time.monotonic()
    while True:
        status = arm.get_arm_status()
        if status is not None and getattr(status.msg, "motion_status", None) == 0:
            return True
        if time.monotonic() - start_t > timeout:
            print(f"等待运动超时（{timeout:.1f}s）")
            return False
        time.sleep(poll_interval)


class RobotArmControl:
    """Nero 机械臂录制与回放控制类。"""

    def __init__(
        self,
        robot="nero",
        comm="can",
        channel="can0",
        json_path="test/nero_arm_records.json",
        sample_interval_s=0.005,
        # ✅ 修复1：固件1.11必须用NeroFW.V111，不能用DEFAULT
        firmware=NeroFW.V111,
    ):
        self._robot = robot
        self._comm = comm
        self._channel = channel
        self._json_path = Path(json_path)
        self._sample_interval_s = sample_interval_s

        arm_cfg = create_agx_arm_config(
            robot=robot,
            comm=comm,
            channel=channel,
            firmeware_version=firmware,  # ✅ 修复1：正确固件版本
        )
        self._arm = AgxArmFactory.create_arm(arm_cfg)

        self._record_thread = None
        self._stop_event = threading.Event()
        self._record_lock = threading.Lock()
        self._records = []
        self._is_recording = False
        self._record_started_at = None
        self._last_can_diag_ts = 0.0

    # ------------------------------------------------------------------ #
    #  连接管理
    # ------------------------------------------------------------------ #

    def connect(self):
        self._arm.connect()
        if not self._arm.is_connected():
            raise RuntimeError("机械臂连接失败...")
        print("机械臂连接成功")

    def disconnect(self):
        self._arm.disconnect()
        if self._arm.is_connected():
            raise RuntimeError("机械臂断开连接失败...")
        print("机械臂已断开连接")

    # ------------------------------------------------------------------ #
    #  状态查询
    # ------------------------------------------------------------------ #

    def get_arm_status(self):
        arm_status = self._arm.get_arm_status()
        if arm_status is not None:
            print(arm_status.msg)
            print(f"hz={arm_status.hz}  ts={arm_status.timestamp}")
        else:
            print("机械臂状态获取失败...")

    def get_firmware(self):
        firmware = self._arm.get_firmware()
        if firmware is not None:
            print("固件信息:", firmware)
        else:
            print("机械臂固件获取失败...")

    # ------------------------------------------------------------------ #
    #  使能 / 模式切换
    # ------------------------------------------------------------------ #

    def reset(self):
        self._arm.reset()

    def _is_can_tx_buffer_error(self, exc: Exception) -> bool:
        text = str(exc)
        return "No buffer space available" in text or "Error Code 105" in text

    def _print_can_diagnostics(self):
        now = time.monotonic()
        # 避免每次失败都刷屏，2秒内最多打印一次。
        if now - self._last_can_diag_ts < 2.0:
            return
        self._last_can_diag_ts = now
        try:
            result = subprocess.run(
                ["ip", "-details", "link", "show", self._channel],
                capture_output=True,
                text=True,
                check=False,
            )
            details = result.stdout.strip() or result.stderr.strip() or "(empty output)"
            print(f"[CAN诊断] {self._channel} 状态:\n{details}")
        except Exception as diag_exc:
            print(f"[CAN诊断] 查询接口状态失败: {diag_exc}")

    def enable(self, timeout: float = 10.0):
        start_t = time.monotonic()
        while True:
            try:
                if self._arm.enable():
                    break
            except RuntimeError as exc:
                if not self._is_can_tx_buffer_error(exc):
                    raise
                print(f"检测到 CAN 发送缓存异常，稍后重试: {exc}")
                self._print_can_diagnostics()

            if time.monotonic() - start_t > timeout:
                raise RuntimeError(
                    f"机械臂使能超时（{timeout:.1f}s）。"
                    f"疑似 CAN 总线发送不可用，请检查 {self._channel} 的链路状态/波特率/布线。"
                )
            print("等待机械臂使能...")
            time.sleep(0.2)
        print("机械臂使能成功")

    def set_leader_mode(self):
        """切换到主臂（零力拖动）模式。"""
        self._arm.set_leader_mode()
        print("已设置主臂模式（可自由拖动）")

    def set_normal_mode(self, enable_after: bool = True, enable_timeout: float = 10.0):
        """
        ✅ 修复3：先发 set_normal_mode，再等待使能成功。
        文档说明：set_normal_mode() 只在 arm 已使能时才能开启 CAN 反馈推送，
        因此切回正常模式后必须重新 enable。
        """
        self._arm.set_normal_mode()
        time.sleep(0.2)  # 给控制器一点时间切换
        if enable_after:
            start_t = time.monotonic()
            while True:
                try:
                    if self._arm.enable():
                        break
                except RuntimeError as exc:
                    if not self._is_can_tx_buffer_error(exc):
                        raise
                    print(f"检测到 CAN 发送缓存异常，稍后重试: {exc}")
                    self._print_can_diagnostics()

                if time.monotonic() - start_t > enable_timeout:
                    raise RuntimeError(
                        f"切换正常模式后使能超时（{enable_timeout:.1f}s）。"
                        f"疑似 CAN 总线发送不可用，请检查 {self._channel}。"
                    )
                time.sleep(0.2)
        print("机械臂已切换为正常模式并使能")

    def set_electronic_emergency_stop(self):
        self._arm.electronic_emergency_stop()

    def move_j(self, joints):
        self._arm.move_j(joints)

    # ------------------------------------------------------------------ #
    #  录制
    # ------------------------------------------------------------------ #

    def start_recording(self):
        if self._is_recording:
            raise RuntimeError("录制已在进行中，无需重复启动。")
        self._stop_event.clear()
        with self._record_lock:
            self._records = []
        self._record_started_at = time.time()
        self._record_thread = threading.Thread(
            target=self._record_loop, name="nero-arm-recorder", daemon=True
        )
        self._is_recording = True
        self._record_thread.start()

    def stop_recording(self, save=True):
        if not self._is_recording:
            return 0
        self._stop_event.set()
        if self._record_thread is not None:
            self._record_thread.join(timeout=2.0)
            if self._record_thread.is_alive():
                raise RuntimeError("录制线程未正常退出。")
        self._is_recording = False
        if save:
            self._save_records_to_json()
        with self._record_lock:
            return len(self._records)

    def record_until_enter(self, prompt="录制中，按回车结束..."):
        self.start_recording()
        print(prompt)
        input()
        count = self.stop_recording(save=True)
        return count

    # ------------------------------------------------------------------ #
    #  回放
    # ------------------------------------------------------------------ #

    def replay_from_json(self, speed_percent: int = 50, use_timing: bool = True):
        """
        回放录制的关节轨迹。

        ✅ 修复2：使用 move_js 而不是 move_j。
            move_j 有轨迹规划，连续发点会互相覆盖，导致大部分帧被跳过。
            move_js 是快速跟随模式（MIT passthrough），专为稠密轨迹回放设计。

        ✅ 修复4：先缓慢运动到第一帧，再开始快速回放，避免起始位置跳变。
        """
        records = self._load_records_from_json()
        if not records:
            raise RuntimeError("录制文件中没有可回放的动作数据。")

        self._arm.set_speed_percent(speed_percent)

        # 先用 move_j 平滑运动到起始位置
        print("正在运动到录制起始位置...")
        self._arm.move_j(records[0]["joints"])
        ok = wait_motion_done(self._arm, timeout=15.0)
        if not ok:
            print("⚠️  运动到起始位置超时，仍继续回放，请注意安全")

        print(f"开始回放 {len(records)} 帧轨迹...")
        last_timestamp = None
        for item in records:
            current_timestamp = item["timestamp"]
            if use_timing and last_timestamp is not None:
                delay = max(0.0, current_timestamp - last_timestamp)
                if delay > 0:
                    time.sleep(delay)

            # ✅ 修复2：用 move_js（快速跟随）而非 move_j（带规划）
            self._arm.move_js(item["joints"])
            last_timestamp = current_timestamp

        print("轨迹回放完成")
        return len(records)

    # ------------------------------------------------------------------ #
    #  内部：录制循环
    # ------------------------------------------------------------------ #

    def _record_loop(self):
        while not self._stop_event.is_set():
            joint_angles = self._arm.get_leader_joint_angles()
            if joint_angles is not None and getattr(joint_angles, "msg", None) is not None:
                joints = [float(a) for a in list(joint_angles.msg)]
                if len(joints) == 7:
                    timestamp = float(
                        getattr(joint_angles, "timestamp", time.time())
                    )
                    with self._record_lock:
                        self._records.append({"timestamp": timestamp, "joints": joints})
            time.sleep(self._sample_interval_s)

    # ------------------------------------------------------------------ #
    #  内部：JSON 读写
    # ------------------------------------------------------------------ #

    def _save_records_to_json(self):
        with self._record_lock:
            records = list(self._records)
        payload = {
            "meta": {
                "robot": self._robot,
                "comm": self._comm,
                "channel": self._channel,
                "sample_interval_s": self._sample_interval_s,
                "record_started_at": self._record_started_at,
                "saved_at": time.time(),
                "record_count": len(records),
            },
            "records": records,
        }
        self._json_path.parent.mkdir(parents=True, exist_ok=True)
        with self._json_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"已保存 {len(records)} 条记录到 {self._json_path}")

    def _load_records_from_json(self):
        if not self._json_path.exists():
            raise RuntimeError(f"未找到录制文件: {self._json_path}")
        with self._json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("records")
        if not isinstance(records, list) or not records:
            raise RuntimeError("录制文件格式错误或 records 为空。")
        parsed = []
        for idx, item in enumerate(records):
            if not isinstance(item, dict):
                raise RuntimeError(f"第 {idx} 条记录格式错误。")
            joints = item.get("joints")
            timestamp = item.get("timestamp")
            if not isinstance(joints, list) or len(joints) != 7:
                raise RuntimeError(f"第 {idx} 条记录 joints 非法，期望7轴。")
            if timestamp is None:
                raise RuntimeError(f"第 {idx} 条记录缺少 timestamp。")
            parsed.append({"timestamp": float(timestamp), "joints": [float(a) for a in joints]})
        return parsed


# ------------------------------------------------------------------ #
#  主流程
# ------------------------------------------------------------------ #

def main():
    # ✅ 修复1：传入正确固件版本
    arm = RobotArmControl(
        channel="can_left",
        json_path="test/nero_arm_records.json",
        firmware=NeroFW.V111,   # 固件1.11 必须用 V111
    )

    print("=" * 50)
    print("步骤 1：连接机械臂")
    arm.connect()

    print("\n步骤 2：使能机械臂")
    arm.enable()
    time.sleep(1)

    print("\n步骤 3：查看固件版本（确认是否1.11）")
    arm.get_firmware()

    print("\n步骤 4：查看当前状态")
    arm.get_arm_status()

    print("\n步骤 5：切换为主臂拖动模式")
    arm.set_leader_mode()
    time.sleep(1)

    print("\n步骤 6：开始示教录制")
    record_count = arm.record_until_enter("请手动拖动机械臂，完成后按回车结束录制。")
    print(f"录制结束，共保存 {record_count} 条记录。")
    time.sleep(1)

    print("\n步骤 7：切回正常模式（含重新使能）")
    # ✅ 修复3：set_normal_mode内部会先发指令再enable，顺序正确
    arm.set_normal_mode(enable_after=True)
    time.sleep(1)
    arm.get_arm_status()

    print("\n步骤 8：回放录制轨迹")
    # ✅ 修复2：内部使用 move_js，先归位再回放
    replay_count = arm.replay_from_json(speed_percent=50, use_timing=True)
    print(f"回放结束，共执行 {replay_count} 条动作。")
    time.sleep(2)

    print("\n步骤 9：紧急停止")
    arm.set_electronic_emergency_stop()
    arm.get_arm_status()
    time.sleep(1)

    print("\n步骤 10：重置并恢复")
    arm.reset()
    time.sleep(2)
    arm.enable()
    arm.set_normal_mode(enable_after=False)
    arm.get_arm_status()

    print("\n步骤 11：断开连接")
    arm.disconnect()
    print("=" * 50)
    print("全部流程完成")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"执行失败: {exc}")
        raise