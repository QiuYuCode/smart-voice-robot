import json
import time

import vosk
import cv2
import speech_recognition as sr

import py_trees
from py_trees import logging as log_tree


# 关闭 ALSA 调试输出
from ctypes import cdll, CFUNCTYPE, c_char_p, c_int
ERROR_HANDLER_FUNC = CFUNCTYPE(
    None, c_char_p, c_int, c_char_p, c_int, c_char_p)

def py_error_handler(filename, line, function, err, fmt):
    pass

c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
try:
    asound = cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(c_error_handler)
except:
    pass


# 1. 定义监听节点 (耳朵)
class ListenForVoice(py_trees.behaviour.Behaviour):
    def __init__(self, name="Listen For Voice"):
        super(ListenForVoice, self).__init__(name)
        self.vosk_model_path = '/home/create/DataDisk/WorkSpace/MyProjects/PythonPlayground/pytree_learing/model/small'
        self.vosk_model = None
        self.recognizer = sr.Recognizer()
        self.microphone = None
        # 初始化黑板客户端，准备写入
        self.blackboard = py_trees.blackboard.Client(name="VoiceClient", namespace="voice")
        self.blackboard.register_key(key="command_text", access=py_trees.common.Access.WRITE)

    def setup(self):
        try:
            vosk.SetLogLevel(-1)
            self.vosk_model = vosk.Model(self.vosk_model_path)
            self.vosk_rec = vosk.KaldiRecognizer()
            self.logger.debug("模型加载完成")
        except Exception as e:
            self.logger.error(f"模型加载失败 {e}")
            
        try:
            self.microphone = sr.Microphone()
            self.logger.info("🎤 麦克风初始化成功...")
        except Exception as e:
            self.logger.error(f"麦克风初始化失败: {e}")

    def update(self):
        self.logger.info("👂 聆听中...")
        
        try:
            with self.microphone as source:
                # 快速调整一下底噪
                self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                
                # 开始录音 (超时设置短一点，避免卡住)
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)

            # 1. 把录音转成字节流
            raw_data = audio.get_raw_data()
            
            # 2. 创建一个临时的识别器 (或者在 setup 里创建并复用)
            # 这里的 16000 是采样率，通常麦克风是 16000 或 44100
            # 我们直接用 source.SAMPLE_RATE 保证匹配
            rec = vosk.KaldiRecognizer(self.vosk_model, source.SAMPLE_RATE)
            
            # 3. 喂数据给识别器
            if rec.AcceptWaveform(raw_data):
                result = rec.Result() # 返回的是 JSON 字符串
                result_dict = json.loads(result)
                text = result_dict.get("text", "")
            else:
                # 如果是部分结果
                result = rec.FinalResult()
                result_dict = json.loads(result)
                text = result_dict.get("text", "")

            # 4. 处理中文空格问题 (Vosk 会把 "打开" 识别成 "打 开")
            text = text.replace(" ", "")
            
            if text:
                self.logger.debug(f"📝 识别结果: '{text}'")
                self.blackboard.command_text = text
                return py_trees.common.Status.SUCCESS
            else:
                return py_trees.common.Status.RUNNING

        except sr.WaitTimeoutError:
            # 没听到声音继续等
            return py_trees.common.Status.RUNNING
        except Exception as e:
            self.logger.error(f"处理出错: {e}")
            return py_trees.common.Status.FAILURE


# 2. 定义检查指令节点 (大脑)
class CheckCommand(py_trees.behaviour.Behaviour):
    def __init__(self, name="Check Command Node"):
        super(CheckCommand, self).__init__(name)
        # 初始化黑板客户端，准备读取
        self.blackboard = py_trees.blackboard.Client(name="CheckClient", namespace="voice")
        self.blackboard.register_key(key="command_text", access=py_trees.common.Access.READ)

    def update(self):
        # 安全获取变量，防止报错
        try:
            cmd = self.blackboard.command_text
            self.logger.debug(f"识别结果 {cmd}")
        except (KeyError, AttributeError):
            cmd = None

        if cmd and ("打开" in cmd and "摄像头" in cmd):
            self.logger.info("✅ 指令匹配成功！")
            return py_trees.common.Status.SUCCESS
        else:
            if cmd:
                self.logger.warning(f"❌ 指令不匹配: {cmd}")
            return py_trees.common.Status.FAILURE


# 3. 定义执行动作节点 (手)
class OpenCamera(py_trees.behaviour.Behaviour):
    def __init__(self, name="Camera Node"):
        super(OpenCamera, self).__init__(name)
        self.cap = None  # 句柄

    def setup(self):
        # 【关键】程序启动时就连接硬件，一直占着不放
        self.logger.info("🔌 [Setup] 正在连接摄像头硬件...")
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.logger.error("无法连接摄像头")
            raise RuntimeError("无法连接摄像头")

    def initialise(self):
        # 任务开始：只需要准备一下窗口
        self.logger.info("🎬 [Init] 任务开始，准备显示画面")

    def update(self):
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
        # 【关键】任务结束：只关闭窗口，但【不】断开摄像头连接
        self.logger.info("⏸️ [Terminate] 任务结束，关闭窗口")
        cv2.destroyAllWindows()
        # 注意：这里没有调用 self.cap.release()！

    def shutdown(self):
        # 【关键】程序退出：彻底释放硬件
        self.logger.warning("💀 [Shutdown] 程序即将退出，释放摄像头资源")
        if self.cap:
            self.cap.release()


# 4. 组装行为树
def create_tree():
    # 根节点：Sequence (序列)
    # memory=False: 意味着如果不处于 RUNNING 状态，每次都从头开始执行
    root = py_trees.composites.Sequence(name="语音助手主程序", memory=True)

    listen = ListenForVoice()
    check = CheckCommand()
    action = OpenCamera()

    root.add_children(
        [
            listen,
            check,
            action
        ]
    )
    return root


# --- 主程序 ---
if __name__ == "__main__":
    log_tree.Level = log_tree.Level.DEBUG
    tree = create_tree()

    print("🤖 系统启动中...")
    # 这一步非常重要，用来连接所有的黑板读写
    tree.setup_with_descendants()

    try:
        while True:
            # 每次循环就是一次“心跳”
            tree.tick_once()

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n🛑 程序已停止")

    finally:
        print("正在清理资源...")
        tree.shutdown()
