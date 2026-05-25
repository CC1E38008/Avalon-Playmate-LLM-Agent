#!/bin/bash
# 阿瓦隆游戏启动脚本
echo "========================================"
echo "  ⚔️  阿瓦隆 AI 大模型对战"
echo "  10人局 | Django + Bootstrap"
echo "========================================"
echo ""
echo "安装依赖..."
pip3 install django --break-system-packages -q 2>/dev/null
echo ""
echo "启动服务器..."
echo "访问地址: http://localhost:8888"
echo ""
python3 manage.py runserver 0.0.0.0:8888
