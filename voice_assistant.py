import json
import time
import threading

import vosk
import cv2
import speech_recognition as sr
import pyttsx3

import py_trees
from py_trees import logging as log_tree


# 关闭 ALSA 调试输出
from ctypes import cdll, CFUNCTYPE, c_char_p, c_int
ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)

def py_error_handler(filename, line, function, err, fmt):
    pass

c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
try:
    asound = cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(c_error_handler)
except:
    pass

MIC_LOCK = threading.Lock()


# ============================================================================
# 1. 唤醒词检测节点
# ============================================================================
class WakeWordDetector(py_trees.behaviour.Behaviour):
    """待机状态下监听唤醒词"""
    def __init__(self, name="WakeWordDetector"):
        super(WakeWordDetector, self).__init__(name)
        self.vosk_model_path = '/home/create/DataDisk/WorkSpace/MyProjects/PythonPlayground/pytree_learing/model/small'
        self.vosk_model = None
        self.recognizer = sr.Recognizer()
        self.microphone = None
        self.blackboard = py_trees.blackboard.Client(name="WakeClient", namespace="dialog")
        self.blackboard.register_key(key="state", access=py_trees.common.Access.WRITE)
        self.blackboard.register_key(key="wake_word_detected", access=py_trees.common.Access.WRITE)

    def setup(self):
        try:
            vosk.SetLogLevel(-1)
            self.vosk_model = vosk.Model(self.vosk_model_path)
            self.logger.debug("Vosk 模型加载完成")
        except Exception as e:
            self.logger.error(f"模型加载失败: {e}")
            
        try:
            self.microphone = sr.Microphone()
            self.logger.info("麦克风初始化成功")
        except Exception as e:
            self.logger.error(f"麦克风初始化失败: {e}")

    def update(self):
        self.logger.info("[待机] 聆听唤醒词...")
        
        try:
            if not MIC_LOCK.acquire(blocking=False):
                return py_trees.common.Status.RUNNING
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=5)

            raw_data = audio.get_raw_data()
            rec = vosk.KaldiRecognizer(self.vosk_model, source.SAMPLE_RATE)
            
            if rec.AcceptWaveform(raw_data):
                result = rec.Result()
                result_dict = json.loads(result)
                text = result_dict.get("text", "")
            else:
                result = rec.FinalResult()
                result_dict = json.loads(result)
                text = result_dict.get("text", "")

            text = text.replace(" ", "")

            if text and any(wake in text for wake in ["你好助手", "小助手", "助手"]):
                self.logger.info(f"✅ 检测到唤醒词: '{text}'")
                self.blackboard.wake_word_detected = True
                self.blackboard.state = "active"
                return py_trees.common.Status.SUCCESS
            else:
                self.logger.info(f"❌ 未检测到唤醒词: '{text}'")
            return py_trees.common.Status.RUNNING

        except sr.WaitTimeoutError:
            return py_trees.common.Status.RUNNING
        except Exception as e:
            self.logger.error(f"唤醒词检测出错: {e}")
            return py_trees.common.Status.RUNNING
        finally:
            if MIC_LOCK.locked():
                MIC_LOCK.release()


# ============================================================================
# 2. 打断监听器节点
# ============================================================================
class InterruptMonitor(py_trees.behaviour.Behaviour):
    """并行监听打断指令"""
    def __init__(self, name="InterruptMonitor"):
        super(InterruptMonitor, self).__init__(name)
        self.recognizer = sr.Recognizer()
        self.microphone = None
        self.vosk_model_path = '/home/create/DataDisk/WorkSpace/MyProjects/PythonPlayground/pytree_learing/model/small'
        self.vosk_model = None
        self.blackboard = py_trees.blackboard.Client(name="InterruptClient", namespace="dialog")
        self.blackboard.register_key(key="interrupt_command", access=py_trees.common.Access.WRITE)
        self.blackboard.register_key(key="state", access=py_trees.common.Access.WRITE)

    def setup(self):
        try:
            vosk.SetLogLevel(-1)
            self.vosk_model = vosk.Model(self.vosk_model_path)
        except Exception as e:
            self.logger.error(f"打断监听器模型加载失败: {e}")
            
        try:
            self.microphone = sr.Microphone()
        except Exception as e:
            self.logger.error(f"打断监听器麦克风初始化失败: {e}")

    def initialise(self):
        # 每次开始监听前清空打断标记
        try:
            self.blackboard.unset("interrupt_command")
        except KeyError:
            pass

    def update(self):
        # 检查黑板上是否已有打断指令
        try:
            if self.blackboard.interrupt_command:
                return py_trees.common.Status.SUCCESS
        except (KeyError, AttributeError):
            pass

        # 快速检测打断词
        try:
            if not MIC_LOCK.acquire(blocking=False):
                return py_trees.common.Status.RUNNING
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.1)
                audio = self.recognizer.listen(source, timeout=0.5, phrase_time_limit=3)

            raw_data = audio.get_raw_data()
            rec = vosk.KaldiRecognizer(self.vosk_model, source.SAMPLE_RATE)
            
            if rec.AcceptWaveform(raw_data):
                result = rec.Result()
                result_dict = json.loads(result)
                text = result_dict.get("text", "")
            else:
                result = rec.FinalResult()
                result_dict = json.loads(result)
                text = result_dict.get("text", "")

            text = text.replace(" ", "")
            
            if text and any(word in text for word in ["停止", "别说了", "退出", "休眠"]):
                self.logger.warning(f"⚠️ 检测到打断指令: '{text}'")
                self.blackboard.interrupt_command = text
                self.blackboard.state = "interrupted"
                return py_trees.common.Status.SUCCESS
            
            return py_trees.common.Status.RUNNING

        except sr.WaitTimeoutError:
            return py_trees.common.Status.RUNNING
        except Exception as e:
            # 静默失败，不阻塞主流程
            return py_trees.common.Status.RUNNING
        finally:
            if MIC_LOCK.locked():
                MIC_LOCK.release()


# ============================================================================
# 3. TTS 播报节点
# ============================================================================
class PlayWakeupSound(py_trees.behaviour.Behaviour):
    """播报唤醒确认"""
    def __init__(self, name="PlayWakeupSound"):
        super(PlayWakeupSound, self).__init__(name)
        self.tts_engine = None
        self.is_speaking = False
        self.thread = None

    def setup(self):
        try:
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', 150)  # 语速
            self.tts_engine.setProperty('volume', 0.9)  # 音量
            self.logger.info("TTS 引擎初始化成功")
        except Exception as e:
            self.logger.error(f"TTS 引擎初始化失败: {e}")

    def initialise(self):
        self.is_speaking = True
        self.thread = None

    def update(self):
        if not self.tts_engine:
            return py_trees.common.Status.FAILURE

        if self.is_speaking and self.thread is None:
            self.logger.info("🔊 [播报] 我在，请说")
            self.thread = threading.Thread(
                target=self._speak,
                args=("我在，请说",),
                daemon=True
            )
            self.thread.start()
            return py_trees.common.Status.RUNNING

        if self.thread and not self.thread.is_alive():
            self.is_speaking = False
            self.thread = None
            return py_trees.common.Status.SUCCESS

        return py_trees.common.Status.RUNNING

    def _speak(self, text):
        self.tts_engine.say(text)
        self.tts_engine.runAndWait()


class PlayResponseSound(py_trees.behaviour.Behaviour):
    """播报执行结果"""
    def __init__(self, name="PlayResponseSound"):
        super(PlayResponseSound, self).__init__(name)
        self.tts_engine = None
        self.is_speaking = False
        self.thread = None
        self.blackboard = py_trees.blackboard.Client(name="ResponseClient", namespace="dialog")
        self.blackboard.register_key(key="response_text", access=py_trees.common.Access.READ)
        self.blackboard.register_key(key="interrupt_command", access=py_trees.common.Access.READ)

    def setup(self):
        try:
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', 150)
            self.tts_engine.setProperty('volume', 0.9)
            self.logger.info("响应 TTS 引擎初始化成功")
        except Exception as e:
            self.logger.error(f"响应 TTS 引擎初始化失败: {e}")

    def initialise(self):
        self.is_speaking = True
        self.thread = None

    def update(self):
        # 检查是否被打断
        try:
            if self.blackboard.interrupt_command:
                self.logger.warning("TTS 被打断")
                return py_trees.common.Status.FAILURE
        except (KeyError, AttributeError):
            pass

        if not self.tts_engine:
            return py_trees.common.Status.FAILURE

        if self.is_speaking and self.thread is None:
            try:
                response = self.blackboard.response_text
            except (KeyError, AttributeError):
                response = "操作完成"
            
            self.logger.info(f"🔊 [播报] {response}")
            self.thread = threading.Thread(
                target=self._speak,
                args=(response,),
                daemon=True
            )
            self.thread.start()
            return py_trees.common.Status.RUNNING

        if self.thread and not self.thread.is_alive():
            self.is_speaking = False
            self.thread = None
            return py_trees.common.Status.SUCCESS

        return py_trees.common.Status.RUNNING

    def _speak(self, text):
        self.tts_engine.say(text)
        self.tts_engine.runAndWait()

    def terminate(self, new_status):
        # 如果被打断，停止 TTS
        if self.tts_engine and self.is_speaking:
            self.tts_engine.stop()
        self.thread = None


# ============================================================================
# 4. 监听用户指令节点
# ============================================================================
class ListenForCommand(py_trees.behaviour.Behaviour):
    """监听用户指令"""
    def __init__(self, name="ListenForCommand"):
        super(ListenForCommand, self).__init__(name)
        self.vosk_model_path = '/home/create/DataDisk/WorkSpace/MyProjects/PythonPlayground/pytree_learing/model/small'
        self.vosk_model = None
        self.recognizer = sr.Recognizer()
        self.microphone = None
        self.blackboard = py_trees.blackboard.Client(name="ListenClient", namespace="dialog")
        self.blackboard.register_key(key="command_text", access=py_trees.common.Access.WRITE)
        self.blackboard.register_key(key="last_activity_time", access=py_trees.common.Access.WRITE)
        self.blackboard.register_key(key="interrupt_command", access=py_trees.common.Access.READ)

    def setup(self):
        try:
            vosk.SetLogLevel(-1)
            self.vosk_model = vosk.Model(self.vosk_model_path)
        except Exception as e:
            self.logger.error(f"指令监听模型加载失败: {e}")
            
        try:
            self.microphone = sr.Microphone()
        except Exception as e:
            self.logger.error(f"指令监听麦克风初始化失败: {e}")

    def update(self):
        # 检查是否被打断
        try:
            if self.blackboard.interrupt_command:
                return py_trees.common.Status.FAILURE
        except (KeyError, AttributeError):
            pass

        self.logger.info("👂 [监听] 等待指令...")
        
        try:
            if not MIC_LOCK.acquire(blocking=False):
                return py_trees.common.Status.RUNNING
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=6)

            raw_data = audio.get_raw_data()
            rec = vosk.KaldiRecognizer(self.vosk_model, source.SAMPLE_RATE)
            
            if rec.AcceptWaveform(raw_data):
                result = rec.Result()
                result_dict = json.loads(result)
                text = result_dict.get("text", "")
            else:
                result = rec.FinalResult()
                result_dict = json.loads(result)
                text = result_dict.get("text", "")

            text = text.replace(" ", "")
            
            if text:
                self.logger.info(f"📝 识别到指令: '{text}'")
                self.blackboard.command_text = text
                self.blackboard.last_activity_time = time.time()
                return py_trees.common.Status.SUCCESS
            else:
                return py_trees.common.Status.RUNNING

        except sr.WaitTimeoutError:
            return py_trees.common.Status.RUNNING
        except Exception as e:
            self.logger.error(f"指令监听出错: {e}")
            return py_trees.common.Status.FAILURE
        finally:
            if MIC_LOCK.locked():
                MIC_LOCK.release()


# ============================================================================
# 5. 意图识别节点
# ============================================================================
class RecognizeIntent(py_trees.behaviour.Behaviour):
    """识别用户意图"""
    def __init__(self, name="RecognizeIntent"):
        super(RecognizeIntent, self).__init__(name)
        self.blackboard = py_trees.blackboard.Client(name="IntentClient", namespace="dialog")
        self.blackboard.register_key(key="command_text", access=py_trees.common.Access.READ)
        self.blackboard.register_key(key="intent", access=py_trees.common.Access.WRITE)

        self.intent_patterns = {
            "open_camera": ["打开", "摄像头"],
            "query_weather": ["天气", "温度"],
            "play_music": ["播放", "音乐"],
            "stop": ["停止", "退出"]
        }

    def update(self):
        try:
            cmd = self.blackboard.command_text
        except (KeyError, AttributeError):
            return py_trees.common.Status.FAILURE

        self.logger.info(f"🧠 [识别] 分析指令: '{cmd}'")

        # 匹配意图
        for intent, keywords in self.intent_patterns.items():
            if all(kw in cmd for kw in keywords):
                self.logger.info(f"✅ 意图匹配: {intent}")
                self.blackboard.intent = intent
                return py_trees.common.Status.SUCCESS

        # 未匹配到已知意图
        self.logger.warning(f"❓ 未能识别意图: {cmd}")
        self.blackboard.intent = "unknown"
        return py_trees.common.Status.SUCCESS


# ============================================================================
# 6. 动作执行节点
# ============================================================================
class OpenCameraAction(py_trees.behaviour.Behaviour):
    """打开摄像头动作"""
    def __init__(self, name="OpenCameraAction"):
        super(OpenCameraAction, self).__init__(name)
        self.cap = None
        self.blackboard = py_trees.blackboard.Client(name="CameraClient", namespace="dialog")
        self.blackboard.register_key(key="intent", access=py_trees.common.Access.READ)
        self.blackboard.register_key(key="response_text", access=py_trees.common.Access.WRITE)
        self.blackboard.register_key(key="interrupt_command", access=py_trees.common.Access.READ)

    def setup(self):
        self.logger.info("连接摄像头硬件...")
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.logger.error("无法连接摄像头")
            raise RuntimeError("无法连接摄像头")

    def initialise(self):
        try:
            intent = self.blackboard.intent
            if intent != "open_camera":
                return
        except (KeyError, AttributeError):
            return
        
        self.logger.info("🎬 [执行] 打开摄像头")
        self.blackboard.response_text = "摄像头已打开，按q关闭"

    def update(self):
        # 检查意图是否匹配
        try:
            intent = self.blackboard.intent
            if intent != "open_camera":
                return py_trees.common.Status.FAILURE
        except (KeyError, AttributeError):
            return py_trees.common.Status.FAILURE

        # 检查是否被打断
        try:
            if self.blackboard.interrupt_command:
                self.logger.warning("摄像头操作被打断")
                return py_trees.common.Status.FAILURE
        except (KeyError, AttributeError):
            pass

        # 实时读取和显示
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                cv2.imshow('Camera', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    return py_trees.common.Status.SUCCESS
                return py_trees.common.Status.RUNNING
        return py_trees.common.Status.FAILURE

    def terminate(self, new_status):
        self.logger.info("关闭摄像头窗口")
        cv2.destroyAllWindows()

    def shutdown(self):
        self.logger.warning("释放摄像头资源")
        if self.cap:
            self.cap.release()


class QueryWeatherAction(py_trees.behaviour.Behaviour):
    """查询天气动作"""
    def __init__(self, name="QueryWeatherAction"):
        super(QueryWeatherAction, self).__init__(name)
        self.blackboard = py_trees.blackboard.Client(name="WeatherClient", namespace="dialog")
        self.blackboard.register_key(key="intent", access=py_trees.common.Access.READ)
        self.blackboard.register_key(key="response_text", access=py_trees.common.Access.WRITE)

    def update(self):
        try:
            intent = self.blackboard.intent
            if intent != "query_weather":
                return py_trees.common.Status.FAILURE
        except (KeyError, AttributeError):
            return py_trees.common.Status.FAILURE

        self.logger.info("🌤️ [执行] 查询天气")
        # 模拟天气查询
        time.sleep(1)
        self.blackboard.response_text = "今天天气晴朗，温度25度"
        return py_trees.common.Status.SUCCESS


class PlayMusicAction(py_trees.behaviour.Behaviour):
    """播放音乐动作"""
    def __init__(self, name="PlayMusicAction"):
        super(PlayMusicAction, self).__init__(name)
        self.blackboard = py_trees.blackboard.Client(name="MusicClient", namespace="dialog")
        self.blackboard.register_key(key="intent", access=py_trees.common.Access.READ)
        self.blackboard.register_key(key="response_text", access=py_trees.common.Access.WRITE)

    def update(self):
        try:
            intent = self.blackboard.intent
            if intent != "play_music":
                return py_trees.common.Status.FAILURE
        except (KeyError, AttributeError):
            return py_trees.common.Status.FAILURE

        self.logger.info("🎵 [执行] 播放音乐")
        # 模拟音乐播放
        time.sleep(1)
        self.blackboard.response_text = "正在为您播放音乐"
        return py_trees.common.Status.SUCCESS


class UnknownCommandResponse(py_trees.behaviour.Behaviour):
    """未知指令响应"""
    def __init__(self, name="UnknownCommandResponse"):
        super(UnknownCommandResponse, self).__init__(name)
        self.blackboard = py_trees.blackboard.Client(name="UnknownClient", namespace="dialog")
        self.blackboard.register_key(key="intent", access=py_trees.common.Access.READ)
        self.blackboard.register_key(key="response_text", access=py_trees.common.Access.WRITE)

    def update(self):
        try:
            intent = self.blackboard.intent
            if intent != "unknown":
                return py_trees.common.Status.FAILURE
        except (KeyError, AttributeError):
            return py_trees.common.Status.FAILURE

        self.logger.warning("❓ [执行] 未能识别指令")
        self.blackboard.response_text = "抱歉，我还不能理解这个指令"
        return py_trees.common.Status.SUCCESS


class StopAction(py_trees.behaviour.Behaviour):
    """停止/退出动作"""
    def __init__(self, name="StopAction"):
        super(StopAction, self).__init__(name)
        self.blackboard = py_trees.blackboard.Client(name="StopClient", namespace="dialog")
        self.blackboard.register_key(key="intent", access=py_trees.common.Access.READ)
        self.blackboard.register_key(key="response_text", access=py_trees.common.Access.WRITE)
        self.blackboard.register_key(key="state", access=py_trees.common.Access.WRITE)

    def update(self):
        try:
            intent = self.blackboard.intent
            if intent != "stop":
                return py_trees.common.Status.FAILURE
        except (KeyError, AttributeError):
            return py_trees.common.Status.FAILURE

        self.logger.info("🛑 [执行] 停止并回到待机")
        self.blackboard.response_text = "已进入待机状态"
        self.blackboard.state = "idle"
        return py_trees.common.Status.SUCCESS


# ============================================================================
# 7. 超时检查节点
# ============================================================================
class CheckDialogTimeout(py_trees.behaviour.Behaviour):
    """检查对话超时"""
    def __init__(self, timeout_seconds=10, name="CheckDialogTimeout"):
        super(CheckDialogTimeout, self).__init__(name)
        self.timeout_seconds = timeout_seconds
        self.blackboard = py_trees.blackboard.Client(name="TimeoutClient", namespace="dialog")
        self.blackboard.register_key(key="last_activity_time", access=py_trees.common.Access.WRITE)
        self.blackboard.register_key(key="state", access=py_trees.common.Access.WRITE)

    def update(self):
        try:
            last_time = self.blackboard.last_activity_time
            elapsed = time.time() - last_time
            
            if elapsed > self.timeout_seconds:
                self.logger.warning(f"⏰ 对话超时 ({elapsed:.1f}s)，回到待机")
                self.blackboard.state = "idle"
                return py_trees.common.Status.FAILURE
            else:
                self.logger.debug(f"对话活跃中 ({elapsed:.1f}s)")
                return py_trees.common.Status.SUCCESS
        except (KeyError, AttributeError):
            # 没有活动时间记录，不算超时
            self.blackboard.last_activity_time = time.time()
            return py_trees.common.Status.SUCCESS


# ============================================================================
# 8. 状态重置节点
# ============================================================================
class ResetDialogState(py_trees.behaviour.Behaviour):
    """重置对话状态"""
    def __init__(self, name="ResetDialogState"):
        super(ResetDialogState, self).__init__(name)
        self.blackboard = py_trees.blackboard.Client(name="ResetClient", namespace="dialog")
        self.blackboard.register_key(key="state", access=py_trees.common.Access.WRITE)

    def update(self):
        self.logger.info("🔄 重置对话状态")
        # 清理黑板
        for key in ["command_text", "intent", "response_text", "interrupt_command", 
                    "wake_word_detected", "last_activity_time"]:
            try:
                self.blackboard.unset(key)
            except KeyError:
                pass
        
        self.blackboard.state = "idle"
        return py_trees.common.Status.SUCCESS


class CheckDialogState(py_trees.behaviour.Behaviour):
    """根据黑板状态决定是否运行分支"""
    def __init__(self, target_state, name="CheckDialogState"):
        super(CheckDialogState, self).__init__(name)
        self.target_state = target_state
        self.blackboard = py_trees.blackboard.Client(name="StateClient", namespace="dialog")
        self.blackboard.register_key(key="state", access=py_trees.common.Access.READ)

    def update(self):
        try:
            current = self.blackboard.state
        except (KeyError, AttributeError):
            current = "idle"
        return (
            py_trees.common.Status.SUCCESS
            if current == self.target_state
            else py_trees.common.Status.FAILURE
        )


# ============================================================================
# 9. 组装行为树
# ============================================================================
def create_tree():
    """创建完整的语音交互行为树"""
    
    init_bb = py_trees.blackboard.Client(name="TreeInit", namespace="dialog")
    init_bb.register_key(key="state", access=py_trees.common.Access.WRITE)
    try:
        _ = init_bb.state
    except (KeyError, AttributeError):
        init_bb.state = "idle"

    # Root: Selector (在待机和激活状态之间切换)
    root = py_trees.composites.Selector(
        name="语音助手根节点",
        memory=False
    )

    # ---- 待机状态分支 ----
    idle_sequence = py_trees.composites.Sequence(
        name="待机分支",
        memory=False
    )
    idle_sequence.add_children([
        CheckDialogState(target_state="idle", name="检查待机状态"),
        WakeWordDetector()
    ])

    # ---- 激活状态分支 ----
    # 使用 Parallel 实现打断功能
    active_parallel = py_trees.composites.Parallel(
        name="激活状态_可打断",
        policy=py_trees.common.ParallelPolicy.SuccessOnOne()
    )

    # 打断监听器（并行运行）
    interrupt_monitor = InterruptMonitor()

    # 对话循环 (Sequence)
    dialog_sequence = py_trees.composites.Sequence(
        name="对话循环",
        memory=False  # 每次完成后重置
    )

    # 对话流程各步骤
    play_wakeup = PlayWakeupSound()
    listen_command = ListenForCommand()
    recognize_intent = RecognizeIntent()

    # 动作执行 (Selector - 根据意图选择动作)
    action_selector = py_trees.composites.Selector(
        name="动作执行选择器",
        memory=False
    )
    action_selector.add_children([
        OpenCameraAction(),
        QueryWeatherAction(),
        PlayMusicAction(),
        StopAction(),
        UnknownCommandResponse()
    ])

    play_response = PlayResponseSound()
    check_timeout = CheckDialogTimeout(timeout_seconds=10)

    # 组装对话序列
    dialog_sequence.add_children([
        play_wakeup,
        listen_command,
        recognize_intent,
        action_selector,
        play_response,
        check_timeout
    ])

    # 组装并行节点
    active_parallel.add_children([
        interrupt_monitor,
        dialog_sequence
    ])

    # 重置状态节点（当激活状态结束时）
    reset_state = ResetDialogState()

    active_guarded = py_trees.composites.Sequence(
        name="激活分支",
        memory=False
    )
    active_guarded.add_children([
        CheckDialogState(target_state="active", name="检查激活状态"),
        active_parallel,
        reset_state
    ])

    # 组装根节点
    root.add_children([
        active_guarded,
        idle_sequence
    ])

    return root


# ============================================================================
# 10. 主程序
# ============================================================================
if __name__ == "__main__":
    log_tree.Level = log_tree.Level.DEBUG
    
    print("=" * 60)
    print("🤖 语音助手系统启动中...")
    print("=" * 60)
    print()
    print("功能说明：")
    print("  1. 待机状态：说 '你好助手' 或 '小助手' 唤醒")
    print("  2. 激活状态：说出指令（如 '打开摄像头'、'查询天气'）")
    print("  3. 打断功能：任何时候说 '停止' 或 '退出' 立即回到待机")
    print("  4. 超时机制：10秒无语音输入自动回到待机")
    print()
    print("按 Ctrl+C 退出程序")
    print("=" * 60)
    print()

    tree = create_tree()
    tree.setup_with_descendants()

    try:
        while True:
            tree.tick_once()
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n")
        print("=" * 60)
        print("🛑 程序已停止")
        print("=" * 60)

    finally:
        print("正在清理资源...")
        tree.shutdown()
        print("清理完成，再见！")
