

# ⚔️ LLM Chat 阿瓦隆桌游 Agent：人工智能深度觉醒对战版 (LLM Agent Avalon WEB Version)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Django-4.2+-green?logo=django" alt="Django">
  <img src="https://img.shields.io/badge/Bootstrap-5.3-purple?logo=bootstrap" alt="Bootstrap">
  <img src="https://img.shields.io/badge/license-MIT-orange" alt="License">
</p>

基于 Django + Bootstrap 的 **阿瓦隆（The Avalon）** 网页版，10 人局，
支持 **多个大语言模型（LLM）扮演 AI 玩家**，与人类玩家同台博弈。

> 每个 AI 玩家由独立的大模型驱动，通过公开发言、投票来隐藏身份、迷惑对手、帮助阵营获胜。

---

## 📸 预览

<img width="1011" height="1616" alt="⚔️ 阿瓦隆 - 游戏结算_202652574715" src="https://github.com/user-attachments/assets/3651d143-1d3c-4079-8120-9a25f6b0a9a3" />
<img width="1121" height="1860" alt="b1453c00fb9b5e36525c47f40c3bc5d0" src="https://github.com/user-attachments/assets/65a4c991-1790-44cc-bc0f-e4970958683a" />



---

## ✨ 特性

- 🎮 **完整阿瓦隆规则** — 10 人局，7 种角色，5 轮任务，暗杀翻盘
- 🤖 **多模型对战** — 支持 1~9 个大模型同时参与，随机分配给 AI 玩家
- 🔌 **兼容 OpenAI API** — 支持 OpenAI / DeepSeek / Qwen / 硅基流动 / 本地 vLLM 等所有兼容接口
- 👁️ **角色视野系统** — 梅林知坏人、派西维尔辨候选人、奥伯伦孤立无援
- 🗡️ **暗杀阶段** — 好人赢 3 轮后刺客猜测梅林翻盘
- 💬 **自然语言博弈** — AI 玩家基于公开信息发言、投票、伪装、演戏
- 👤 **人类参与** — 玩家随机扮演一个角色，与 AI 同台竞技
- 📊 **胜率统计** — 按模型统计胜率，日志持久化到 `game_results_of_LLM.log`
- 🎨 **深色玻璃拟态 UI** — Bootstrap 5 + 自定义 CSS 变量，毛玻璃卡片，微交互动画
- 🔒 **信息隔离** — LLM 的私有角色知识不会泄露给其他玩家

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- pip

### 安装

```bash
# 克隆仓库
git clone https://github.com/CC1E38008/Avalon-Playmate-LLM-Agent.git
cd Avalon-Playmate-LLM-Agent

# 安装依赖
pip install django --break-system-packages
# 或
pip install -r requirements.txt
```

### 启动

```bash
chmod +x ./manage.py
python3 manage.py runserver 0.0.0.0:8888

or

chmod +x ./run.sh
chmod +x ./manage.py
./run.sh
```

浏览器打开 `http://localhost:8888`

---

## 🎮 玩法说明

### 角色配置（10 人局）

| 阵营 | 角色 | 人数 | 特殊能力 |
|:---:|------|:---:|------|
| 🛡️ 好人 | 🔮 **梅林** | 1 | 知道所有坏人（除莫德雷德）；必须隐藏身份 |
| 🛡️ 好人 | 👁️ **派西维尔** | 1 | 知道梅林和莫甘娜（分不清谁是谁） |
| 🛡️ 好人 | 🛡️ **忠臣** | 4 | 无特殊信息 |
| 💀 坏人 | 🎭 **莫甘娜** | 1 | 伪装梅林迷惑派西维尔 |
| 💀 坏人 | 🗡️ **刺客** | 1 | 游戏结束时暗杀梅林翻盘 |
| 💀 坏人 | 🕶️ **莫德雷德** | 1 | 梅林看不到他 |
| 💀 坏人 | ❓ **奥伯伦** | 1 | 孤立坏人，互不知道 |

### 游戏流程

1. **设置** — 输入 1~9 个大模型的 API 地址、模型名、API Key
2. **角色分配** — 10 个角色随机分配给 1 个人类 + 9 个 AI
3. **5 轮任务** — 每轮：队长选人 → 讨论发言 → 全体投票 → 执行任务
4. **胜利条件** — 好人赢 3 轮 → 触发暗杀；坏人赢 3 轮 → 直接获胜
5. **暗杀阶段** — 刺客猜测谁是梅林，猜中则坏人翻盘

### 任务参数

| 轮次 | 队伍人数 | 失败需票数 |
|:---:|:---:|:---:|
| 第 1 轮 | 3 | 1 |
| 第 2 轮 | 4 | 1 |
| 第 3 轮 | 4 | 1 |
| 第 4 轮 | 5 | **2** |
| 第 5 轮 | 5 | 1 |

- 连续 **5 次** 队伍投票被拒 → 坏人直接获胜

---

## 📁 项目结构

```
avalon_game/
├── manage.py                     # Django 入口
├── requirements.txt              # 依赖列表
├── run.sh                        # 一键启动脚本
├── game_results_of_LLM.log       # 模型胜率日志（自动生成）
├── avalon_game/
│   ├── settings.py               # Django 配置（CSRF 已注释）
│   ├── urls.py                   # 根路由
│   └── wsgi.py
└── game/
    ├── game_state.py             # 🔥 阿瓦隆核心逻辑（~900 行）
    │   ├── 角色分配 & 视野系统
    │   ├── 游戏状态机（9 阶段）
    │   ├── AI 行为（发言/投票/选人/暗杀）
    │   └── 胜利条件判定
    ├── llm_client.py             # 🔌 多 LLM 客户端管理
    │   ├── 连接状态检测
    │   ├── OpenAI 兼容 API 调用
    │   └── 并发 LLM 管理
    ├── views.py                  # Django 视图 & API
    ├── urls.py                   # 路由
    └── templates/game/
        ├── index.html            # 设置页面
        ├── game.html             # 游戏主界面
        └── result.html           # 结算页面（86400s 不倒计时）
```

---

## 🔧 支持的 LLM 接口

兼容所有 **OpenAI Chat Completions** 格式的 API：

| 平台 | Endpoint 示例 |
|------|-------------|
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| 阿里百炼 (Qwen) | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 硅基流动 (SiliconFlow) | `https://api.siliconflow.cn/v1` |
| 智谱 (GLM) | `https://open.bigmodel.cn/api/paas/v4` |
| 本地 vLLM | `http://localhost:8000/v1` |
| Ollama | `http://localhost:11434/v1` |

---

## 📊 模型胜率统计

每局游戏结束后，结果自动追加到 `game_results_of_LLM.log`（JSON Lines 格式）：

```json
{
  "game_id": "a1b2c3d4e5f6",
  "winner": "good",
  "players": [
    {"name": "U", "role": "merlin", "team": "good", "llm_name": "人类"},
    {"name": "A", "role": "assassin", "team": "evil", "llm_name": "GPT-4o"}
  ],
  "llm_stats": {
    "0": {"name": "GPT-4o", "model": "gpt-4o", "wins": 2, "total_players": 3, "win_rate": 0.667}
  }
}
```

## 🤝 贡献

欢迎提 Issue 和 PR！主要改进方向：

- [ ] WebSocket 实时推送（替代轮询）
- [ ] 多轮游戏连胜率追踪
- [ ] 更多角色配置（如 8 人局、湖上夫人扩展）
- [ ] LLM 响应缓存
- [ ] Docker 部署支持

---

## 📜 License

MIT License — 自由使用、修改、分发。

---

<p align="center">
  <sub>Made with ❤️ by AI + Human collaboration</sub>
</p>

