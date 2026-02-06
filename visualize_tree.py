"""
行为树可视化脚本

生成语音助手行为树的图形化表示
"""

import py_trees
import py_trees.display as display


def create_simplified_tree():
    """创建简化版的行为树用于可视化"""
    
    # Root: Selector
    root = py_trees.composites.Selector(
        name="VoiceAssistant_Root",
        memory=True
    )

    # 待机状态
    idle = py_trees.behaviours.StatusQueue(
        name="IdleState_WakeWordDetector",
        queue=[py_trees.common.Status.RUNNING],
        eventually=py_trees.common.Status.SUCCESS
    )

    # 激活状态序列
    active_sequence = py_trees.composites.Sequence(
        name="ActiveState_Sequence",
        memory=False
    )

    # 并行节点（打断支持）
    parallel = py_trees.composites.Parallel(
        name="Parallel_Interruptible",
        policy=py_trees.common.ParallelPolicy.SuccessOnOne()
    )

    # 打断监听器
    interrupt = py_trees.behaviours.StatusQueue(
        name="InterruptMonitor",
        queue=[py_trees.common.Status.RUNNING],
        eventually=py_trees.common.Status.SUCCESS
    )

    # 对话循环序列
    dialog_sequence = py_trees.composites.Sequence(
        name="DialogLoop_Sequence",
        memory=False
    )

    # 对话步骤
    wakeup_sound = py_trees.behaviours.Success(name="PlayWakeupSound")
    listen = py_trees.behaviours.Success(name="ListenForCommand")
    recognize = py_trees.behaviours.Success(name="RecognizeIntent")
    
    # 动作选择器
    action_selector = py_trees.composites.Selector(
        name="ActionSelector",
        memory=False
    )
    
    camera = py_trees.behaviours.Success(name="OpenCameraAction")
    weather = py_trees.behaviours.Success(name="QueryWeatherAction")
    music = py_trees.behaviours.Success(name="PlayMusicAction")
    unknown = py_trees.behaviours.Success(name="UnknownCommandResponse")
    
    action_selector.add_children([camera, weather, music, unknown])
    
    response_sound = py_trees.behaviours.Success(name="PlayResponseSound")
    timeout_check = py_trees.behaviours.Success(name="CheckDialogTimeout")
    
    # 组装对话序列
    dialog_sequence.add_children([
        wakeup_sound,
        listen,
        recognize,
        action_selector,
        response_sound,
        timeout_check
    ])

    # 组装并行节点
    parallel.add_children([
        interrupt,
        dialog_sequence
    ])

    # 重置状态
    reset = py_trees.behaviours.Success(name="ResetDialogState")

    # 组装激活序列
    active_sequence.add_children([
        parallel,
        reset
    ])

    # 组装根节点
    root.add_children([
        idle,
        active_sequence
    ])

    return root


def generate_ascii_tree():
    """生成 ASCII 字符树"""
    tree = create_simplified_tree()
    print("\n" + "=" * 80)
    print("语音助手行为树结构 (ASCII)")
    print("=" * 80)
    print()
    print(py_trees.display.unicode_tree(tree, show_status=True))
    print()


def generate_dot_graph():
    """生成 DOT 图形文件"""
    tree = create_simplified_tree()
    
    try:
        display.render_dot_tree(
            tree,
            name="voice_assistant_tree",
            target_directory="/home/create/WorkSpace/MyProjects/PythonPlayground/pytree_learing"
        )
        print("✅ DOT 图形已生成: voice_assistant_tree.png")
        print("   (需要安装 graphviz: sudo apt-get install graphviz)")
    except Exception as e:
        print(f"❌ DOT 图形生成失败: {e}")
        print("   提示: 确保已安装 graphviz")


def print_structure_diagram():
    """打印结构图"""
    print("\n" + "=" * 80)
    print("行为树结构详解")
    print("=" * 80)
    print("""
Root (Selector, memory=True)
├─ [优先级1] IdleState - WakeWordDetector
│  └─ 待机状态，持续监听唤醒词
│     ├─ RUNNING: 未检测到唤醒词，继续监听
│     └─ SUCCESS: 检测到唤醒词，切换到激活状态
│
└─ [优先级2] ActiveState - Sequence
   ├─ Parallel (SuccessOnOne) - 可打断的对话流程
   │  ├─ [并行子线程1] InterruptMonitor
   │  │  └─ 持续监听打断指令（"停止"、"退出"等）
   │  │     ├─ RUNNING: 无打断指令
   │  │     └─ SUCCESS: 检测到打断指令 → 终止整个 Parallel
   │  │
   │  └─ [并行子线程2] DialogLoop - Sequence (memory=False)
   │     ├─ [步骤1] PlayWakeupSound
   │     │  └─ 播报 "我在，请说"
   │     │
   │     ├─ [步骤2] ListenForCommand
   │     │  └─ 监听用户指令
   │     │     ├─ SUCCESS: 识别到语音
   │     │     └─ FAILURE: 超时无输入
   │     │
   │     ├─ [步骤3] RecognizeIntent
   │     │  └─ 识别用户意图
   │     │     ├─ open_camera
   │     │     ├─ query_weather
   │     │     ├─ play_music
   │     │     └─ unknown
   │     │
   │     ├─ [步骤4] ActionSelector - Selector
   │     │  ├─ OpenCameraAction (intent == "open_camera")
   │     │  ├─ QueryWeatherAction (intent == "query_weather")
   │     │  ├─ PlayMusicAction (intent == "play_music")
   │     │  └─ UnknownCommandResponse (兜底节点)
   │     │
   │     ├─ [步骤5] PlayResponseSound
   │     │  └─ 播报执行结果
   │     │
   │     └─ [步骤6] CheckDialogTimeout
   │        └─ 检查是否超时
   │           ├─ SUCCESS: 未超时，继续循环（回到步骤2）
   │           └─ FAILURE: 已超时，退出对话循环
   │
   └─ ResetDialogState
      └─ 清理黑板数据，重置状态为 idle

---

关键机制说明：

1. **Selector (Root)**
   - 优先执行 IdleState（待机）
   - 当 IdleState 返回 SUCCESS（检测到唤醒词），执行 ActiveState
   - memory=True 保持状态，避免频繁重置

2. **Parallel (打断支持)**
   - SuccessOnOne 策略：任一子节点 SUCCESS，整个节点立即 SUCCESS
   - InterruptMonitor 检测到打断 → 返回 SUCCESS → 终止 DialogLoop
   - 实现了随时打断的功能

3. **Sequence (对话循环)**
   - memory=False：每次完成后重置，支持连续对话
   - 顺序执行：播报 → 监听 → 识别 → 执行 → 播报 → 超时检查
   - 任一步骤 FAILURE 会终止序列

4. **Selector (动作选择)**
   - 根据 intent 选择对应的动作节点
   - 第一个 SUCCESS 的节点执行，其余跳过
   - UnknownCommandResponse 作为兜底，始终返回 SUCCESS

5. **状态流转**
   - 待机 → 唤醒 → 对话循环 → 超时/打断 → 重置 → 待机
   - 黑板（Blackboard）用于节点间数据传递
    """)


def print_blackboard_structure():
    """打印黑板数据结构"""
    print("\n" + "=" * 80)
    print("黑板（Blackboard）数据结构")
    print("=" * 80)
    print("""
namespace = "dialog"

数据变量：
┌─────────────────────┬──────────────────┬─────────────────────────────┐
│ 变量名               │ 类型             │ 用途                         │
├─────────────────────┼──────────────────┼─────────────────────────────┤
│ state               │ str              │ 全局状态: idle/active/      │
│                     │                  │ interrupted                 │
├─────────────────────┼──────────────────┼─────────────────────────────┤
│ wake_word_detected  │ bool             │ 是否检测到唤醒词             │
├─────────────────────┼──────────────────┼─────────────────────────────┤
│ command_text        │ str              │ 用户指令文本                 │
├─────────────────────┼──────────────────┼─────────────────────────────┤
│ intent              │ str              │ 识别的意图类型               │
├─────────────────────┼──────────────────┼─────────────────────────────┤
│ interrupt_command   │ str              │ 打断指令文本                 │
├─────────────────────┼──────────────────┼─────────────────────────────┤
│ last_activity_time  │ float            │ 最后活动时间戳（超时判断）   │
├─────────────────────┼──────────────────┼─────────────────────────────┤
│ response_text       │ str              │ 待播报的响应文本             │
└─────────────────────┴──────────────────┴─────────────────────────────┘

数据流向：

WakeWordDetector → wake_word_detected, state
                    ↓
ListenForCommand → command_text, last_activity_time
                    ↓
RecognizeIntent → intent
                    ↓
ActionNodes → response_text
                    ↓
PlayResponseSound ← response_text

InterruptMonitor → interrupt_command (任何时候)
                    ↓
                所有节点 ← 检查 interrupt_command

CheckDialogTimeout ← last_activity_time
                    ↓
ResetDialogState → 清理所有变量，重置 state = "idle"
    """)


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                  语音助手行为树可视化工具                             ║
╚══════════════════════════════════════════════════════════════════════╝
    """)

    # 生成 ASCII 树
    generate_ascii_tree()

    # 打印结构详解
    print_structure_diagram()

    # 打印黑板结构
    print_blackboard_structure()

    # 生成 DOT 图形
    print("\n" + "=" * 80)
    print("生成图形化表示")
    print("=" * 80)
    generate_dot_graph()

    print("\n" + "=" * 80)
    print("✅ 可视化完成")
    print("=" * 80)
    print("""
提示：
1. 查看上方的 ASCII 树结构了解基本布局
2. 查看详细的结构说明理解每个节点的作用
3. 如果安装了 graphviz，可以查看生成的 PNG 图形
4. 黑板数据结构说明了节点间的数据传递方式
    """)


if __name__ == "__main__":
    main()
