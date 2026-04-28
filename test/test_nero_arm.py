import json
import threading
import time
from pathlib import Path

from pyAgxArm import AgxArmFactory, create_agx_arm_config


class RobotArmControl:
    """Nero 机械臂录制与回放控制类。"""

    def __init__(
        self,
        robot="nero",
        comm="can",
        channel="can_left",
        json_path="test/nero_arm_records.json",
        sample_interval_s=0.005,
    ):
        self._robot = robot
        self._comm = comm
        self._channel = channel
        self._json_path = Path(json_path)
        self._sample_interval_s = sample_interval_s

        arm_cfg = create_agx_arm_config(robot=robot, comm=comm, channel=channel)
        self._arm = AgxArmFactory.create_arm(arm_cfg)

        self._record_thread = None
        self._stop_event = threading.Event()
        self._record_lock = threading.Lock()
        self._records = []
        self._is_recording = False
        self._record_started_at = None

    def connect(self):
        self._arm.connect()

    def reset(self):
        self._arm.reset()
        
    def enable(self):
        while not self._arm.enable():
            print("等待机械臂使能成功...")
            time.sleep(0.1)
        print("机械臂使能成功...")
    
    def set_leader_mode(self):
        self._arm.set_leader_mode()
        
    def set_normal_mode(self):
        while not self._arm.set_normal_mode():
            print("等待机械臂设置为正常模式成功...")
            time.sleep(0.01)
        print("机械臂设置为正常模式成功...")
        
    def set_electronic_emergency_stop(self):
        self._arm.electronic_emergency_stop()
        
    def move_j(self, joints):
        self._arm.move_j(joints)

    def start_recording(self):
        if self._is_recording:
            raise RuntimeError("录制已在进行中，无需重复启动。")

        self._stop_event.clear()
        with self._record_lock:
            self._records = []
        self._record_started_at = time.time()
        self._record_thread = threading.Thread(target=self._record_loop, name="nero-arm-recorder")
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
        return self.stop_recording(save=True)

    def replay_from_json(self, speed_percent=None, use_timing=True):
        records = self._load_records_from_json()
        if not records:
            raise RuntimeError("录制文件中没有可回放的动作数据。")

        if speed_percent is not None:
            self._arm.set_speed_percent(speed_percent)

        last_timestamp = None
        for item in records:
            current_timestamp = item["timestamp"]
            if use_timing and last_timestamp is not None:
                delay = max(0.0, current_timestamp - last_timestamp)
                if delay > 0:
                    time.sleep(delay)

            self.move_j(item["joints"])
            last_timestamp = current_timestamp

        return len(records)

    def _record_loop(self):
        while not self._stop_event.is_set():
            joint_angles = self._arm.get_leader_joint_angles()
            if joint_angles is not None and getattr(joint_angles, "msg", None) is not None:
                joints = [float(angle) for angle in list(joint_angles.msg)]
                if len(joints) == 7:
                    timestamp = float(getattr(joint_angles, "timestamp", time.time()))
                    with self._record_lock:
                        self._records.append({"timestamp": timestamp, "joints": joints})

            time.sleep(self._sample_interval_s)

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

    def _load_records_from_json(self):
        if not self._json_path.exists():
            raise RuntimeError(f"未找到录制文件: {self._json_path}")

        with self._json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        records = data.get("records")
        if not isinstance(records, list) or not records:
            raise RuntimeError("录制文件格式错误或 records 为空。")

        parsed_records = []
        for idx, item in enumerate(records):
            if not isinstance(item, dict):
                raise RuntimeError(f"第 {idx} 条记录格式错误。")

            joints = item.get("joints")
            timestamp = item.get("timestamp")
            if not isinstance(joints, list) or len(joints) != 7:
                raise RuntimeError(f"第 {idx} 条记录 joints 非法，期望 7 轴。")
            if timestamp is None:
                raise RuntimeError(f"第 {idx} 条记录缺少 timestamp。")

            parsed_records.append(
                {
                    "timestamp": float(timestamp),
                    "joints": [float(angle) for angle in joints],
                }
            )

        return parsed_records



def main():
    arm = RobotArmControl(channel="can_left", json_path="test/nero_arm_records.json")
    
    print("1. 连接机械臂...")
    arm.connect()
    
    # print("2. 使能机械臂中...")  
    # arm.enable()
    
    # print("重置机械臂...")
    arm.reset()
    time.sleep(3)
    
    print("2. 设置机械臂为正常模式...")
    arm.set_normal_mode()
    time.sleep(3)
    
    print("2. 设置机械臂为使能模式")
    arm.enable()
    
    print("3. 设置机械臂为主臂模式...")
    arm.set_leader_mode()
    
    print("4. 开始录制主臂关节角...")
    record_count = arm.record_until_enter("请手动操作机械臂，完成后按回车结束录制。")
    print(f"录制结束，共保存 {record_count} 条记录。")
    
    time.sleep(3)
    
    print("开始回放录制动作...")
    print("5. 设置机械臂为正常模式...")
    arm.set_normal_mode()
    time.sleep(3)
    
    replay_count = arm.replay_from_json(speed_percent=50, use_timing=True)
    print(f"回放结束，共执行 {replay_count} 条动作。")
    time.sleep(3)
    
    print("6. 紧急停止机械臂...")
    arm.set_electronic_emergency_stop()
    time.sleep(3)
    
    print("7. 设置机械臂为正常模式...")
    arm.set_normal_mode()
    time.sleep(3)
        
    print("8. 重置机械臂...")
    arm.reset()
    time.sleep(3)

    print("9. 使能机械臂...")
    arm.enable()
    
    print("10. 恢复到普通模式...")
    arm.set_normal_mode()
    time.sleep(3)
        
if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"执行失败: {exc}")