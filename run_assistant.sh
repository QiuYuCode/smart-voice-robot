#!/bin/bash
# 语音助手快速启动脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           语音助手系统 - 启动脚本                         ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检查 Python 版本
echo -e "${YELLOW}[1/5] 检查 Python 版本...${NC}"
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓ Python 版本: $python_version${NC}"
echo ""

# 检查依赖
echo -e "${YELLOW}[2/5] 检查依赖包...${NC}"
required_packages=("py_trees" "vosk" "speech_recognition" "pyttsx3" "cv2")
missing_packages=()

for package in "${required_packages[@]}"; do
    if python3 -c "import $package" 2>/dev/null; then
        echo -e "${GREEN}✓ $package 已安装${NC}"
    else
        echo -e "${RED}✗ $package 未安装${NC}"
        missing_packages+=("$package")
    fi
done

if [ ${#missing_packages[@]} -gt 0 ]; then
    echo ""
    echo -e "${RED}缺少依赖包，请运行：${NC}"
    echo -e "${YELLOW}  uv sync${NC}"
    echo -e "${YELLOW}  # 或${NC}"
    echo -e "${YELLOW}  pip install pyttsx3${NC}"
    exit 1
fi
echo ""

# 检查 Vosk 模型
echo -e "${YELLOW}[3/5] 检查 Vosk 模型...${NC}"
model_path="/home/create/DataDisk/WorkSpace/MyProjects/PythonPlayground/pytree_learing/model/small"
if [ -d "$model_path" ]; then
    echo -e "${GREEN}✓ Vosk 模型存在: $model_path${NC}"
else
    echo -e "${RED}✗ Vosk 模型不存在: $model_path${NC}"
    echo ""
    echo -e "${YELLOW}请下载 Vosk 中文模型：${NC}"
    echo -e "${BLUE}  wget https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip${NC}"
    echo -e "${BLUE}  unzip vosk-model-small-cn-0.22.zip -d model/${NC}"
    exit 1
fi
echo ""

# 检查麦克风
echo -e "${YELLOW}[4/5] 检查麦克风设备...${NC}"
if python3 -c "import speech_recognition as sr; sr.Microphone()" 2>/dev/null; then
    echo -e "${GREEN}✓ 麦克风设备可用${NC}"
else
    echo -e "${RED}✗ 麦克风设备不可用${NC}"
    echo -e "${YELLOW}提示: 请检查麦克风连接${NC}"
fi
echo ""

# 检查 TTS
echo -e "${YELLOW}[5/5] 检查 TTS 引擎...${NC}"
if command -v espeak &> /dev/null; then
    echo -e "${GREEN}✓ espeak 已安装${NC}"
else
    echo -e "${YELLOW}⚠ espeak 未安装，TTS 可能无法工作${NC}"
    echo -e "${YELLOW}安装命令: sudo apt-get install espeak${NC}"
fi
echo ""

# 显示使用提示
echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}使用说明：${NC}"
echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}1.${NC} 说 ${YELLOW}'你好助手'${NC} 或 ${YELLOW}'小助手'${NC} 唤醒系统"
echo -e "  ${GREEN}2.${NC} 支持的指令："
echo -e "     - ${YELLOW}'打开摄像头'${NC}: 显示实时画面"
echo -e "     - ${YELLOW}'查询天气'${NC}: 获取天气信息"
echo -e "     - ${YELLOW}'播放音乐'${NC}: 播放音乐"
echo -e "  ${GREEN}3.${NC} 打断: 随时说 ${YELLOW}'停止'${NC} 或 ${YELLOW}'退出'${NC} 回到待机"
echo -e "  ${GREEN}4.${NC} 超时: 10秒无输入自动回到待机"
echo -e "  ${GREEN}5.${NC} 退出: 按 ${YELLOW}Ctrl+C${NC}"
echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
echo ""

# 询问是否启动
read -p "$(echo -e ${GREEN}准备就绪，是否启动语音助手？ [Y/n]: ${NC})" confirm
confirm=${confirm:-Y}

if [[ $confirm =~ ^[Yy]$ ]]; then
    echo ""
    echo -e "${GREEN}启动语音助手...${NC}"
    echo ""
    python3 voice_assistant.py
else
    echo -e "${YELLOW}已取消启动${NC}"
    exit 0
fi
