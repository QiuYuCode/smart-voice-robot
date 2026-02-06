#!/usr/bin/env python3
"""
语音助手测试脚本

测试场景：
1. 待机状态监听唤醒词
2. 唤醒后执行指令
3. 打断功能测试
4. 超时自动待机测试
"""

import sys
import time


def print_test_header(test_name):
    print("\n" + "=" * 60)
    print(f"🧪 测试: {test_name}")
    print("=" * 60)


def test_wake_cycle():
    """测试待机-唤醒-待机循环"""
    print_test_header("待机-唤醒-待机循环")
    print("""
测试步骤：
1. 启动程序后，系统进入待机状态
2. 说 "你好助手" 或 "小助手" 唤醒系统
3. 听到 "我在，请说" 表示唤醒成功
4. 10秒内不说话，系统自动回到待机状态

预期行为：
- [待机] 聆听唤醒词... (持续显示)
- [检测到] "你好助手"
- [播报] "我在，请说"
- [监听] 等待指令... (超时)
- [待机] 回到待机状态

测试命令：
  python voice_assistant.py
  
  说 "你好助手" → 等待10秒（不说话）→ 观察是否回到待机
    """)


def test_camera_command():
    """测试摄像头指令"""
    print_test_header("打开摄像头指令")
    print("""
测试步骤：
1. 说 "你好助手" 唤醒
2. 听到 "我在，请说" 后，说 "打开摄像头"
3. 观察摄像头窗口是否打开
4. 按 'q' 关闭摄像头
5. 系统播报后继续监听

预期行为：
- [待机] → 唤醒 → [监听] → [识别] "打开摄像头"
- [执行] 打开摄像头窗口
- [播报] "摄像头已打开，按q关闭"
- 摄像头窗口显示实时画面
- 按 'q' 关闭后继续监听下一个指令

测试命令：
  python voice_assistant.py
  
  说 "你好助手" → "打开摄像头" → 按 'q' → 观察是否继续监听
    """)


def test_weather_music():
    """测试天气和音乐指令"""
    print_test_header("天气/音乐查询指令")
    print("""
测试步骤：
1. 说 "你好助手" 唤醒
2. 说 "查询天气" 或 "今天天气"
3. 听到天气播报
4. 说 "播放音乐"
5. 听到音乐播报

预期行为：
- 天气指令: "今天天气晴朗，温度25度"
- 音乐指令: "正在为您播放音乐"
- 每次播报后继续监听

测试命令：
  python voice_assistant.py
  
  说 "你好助手" → "查询天气" → "播放音乐"
    """)


def test_interrupt():
    """测试打断功能"""
    print_test_header("打断功能")
    print("""
测试步骤：
1. 说 "你好助手" 唤醒
2. 说 "打开摄像头"
3. 在摄像头运行时，说 "停止" 或 "退出"
4. 观察摄像头是否立即关闭并回到待机

预期行为：
- [执行] 摄像头正在运行...
- 用户说 "停止"
- ⚠️ 检测到打断指令: '停止'
- 摄像头窗口关闭
- 🔄 重置对话状态
- [待机] 回到待机状态

测试命令：
  python voice_assistant.py
  
  说 "你好助手" → "打开摄像头" → "停止" → 观察是否立即回到待机
    """)


def test_unknown_command():
    """测试未知指令"""
    print_test_header("未知指令处理")
    print("""
测试步骤：
1. 说 "你好助手" 唤醒
2. 说一个未定义的指令，如 "打开电视"
3. 观察系统响应

预期行为：
- [识别] 未能识别意图
- [播报] "抱歉，我还不能理解这个指令"
- 继续监听下一个指令

测试命令：
  python voice_assistant.py
  
  说 "你好助手" → "打开电视" → 听到"抱歉..."
    """)


def test_timeout():
    """测试超时机制"""
    print_test_header("超时自动待机")
    print("""
测试步骤：
1. 说 "你好助手" 唤醒
2. 不说任何指令，等待10秒
3. 观察系统是否自动回到待机

预期行为：
- [监听] 等待指令... (10秒超时)
- ⏰ 对话超时，回到待机
- 🔄 重置对话状态
- [待机] 聆听唤醒词...

测试命令：
  python voice_assistant.py
  
  说 "你好助手" → 保持安静10秒 → 观察超时提示
    """)


def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║           语音助手系统 - 测试指南                         ║
╚══════════════════════════════════════════════════════════╝
    """)

    tests = [
        ("1", "待机-唤醒-待机循环", test_wake_cycle),
        ("2", "打开摄像头指令", test_camera_command),
        ("3", "天气/音乐查询", test_weather_music),
        ("4", "打断功能", test_interrupt),
        ("5", "未知指令处理", test_unknown_command),
        ("6", "超时自动待机", test_timeout),
    ]

    print("可用测试场景：")
    for num, name, _ in tests:
        print(f"  {num}. {name}")
    print("  0. 运行所有测试说明")
    print()

    try:
        choice = input("选择测试场景 (0-6): ").strip()
        
        if choice == "0":
            for _, _, test_func in tests:
                test_func()
        else:
            for num, _, test_func in tests:
                if choice == num:
                    test_func()
                    break
            else:
                print("无效选择")
    except KeyboardInterrupt:
        print("\n\n测试已取消")
        sys.exit(0)

    print("\n" + "=" * 60)
    print("📝 测试完成后的检查点：")
    print("=" * 60)
    print("""
✓ 唤醒词能否正确识别
✓ TTS 播报是否正常
✓ 指令识别是否准确
✓ 动作执行是否符合预期
✓ 打断功能是否立即响应
✓ 超时机制是否自动触发
✓ 状态切换是否流畅

如果遇到问题，检查：
- 麦克风是否正常工作
- Vosk 模型路径是否正确
- TTS 引擎是否已安装 (pyttsx3)
- 摄像头是否可用
    """)


if __name__ == "__main__":
    main()
