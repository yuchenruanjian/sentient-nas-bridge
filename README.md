# sentient-nas-bridge

**WorkBuddy + SentientOS + NAS 三角整合工程**

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   SentientOS    │────▶│      NAS         │◀────│   WorkBuddy     │
│  凌晨3点自动整理  │ 写入 │   持久化知识中枢    │ 读取 │   白天分析执行    │
│  本机数据→精华    │     │  SMB/NFS 挂载     │     │   写入工作记忆    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## 架构

| 组件 | 角色 | 说明 |
|------|------|------|
| **SentientOS** | 数据生产者 | 夜间扫描 iMessage、备忘录、截图等，产出 Markdown 摘要 |
| **NAS** | 知识中枢 | SMB 挂载到 Mac，统一存放知识文件 |
| **WorkBuddy** | 数据消费者 | 读取 NAS 知识库，注入对话上下文，写入工作日志 |

## 目录结构

```
sentient-nas-bridge/
├── config/
│   └── nas.yaml           # NAS 连接配置模板
├── scripts/
│   ├── mount_nas.sh       # 挂载 NAS 到本地
│   └── sync_sentient_to_nas.sh  # Sentient → NAS 同步
├── workbuddy/
│   └── memory_bridge.py   # 记忆桥接 Python 模块
├── .github/workflows/
│   └── sync.yml           # 每日自动同步 CI
└── README.md
```

## 快速开始

### 1. 挂载 NAS

```bash
# 配置环境变量
export NAS_IP="192.168.x.x"
export NAS_SHARE="knowledge"
export NAS_USER="your_user"
export NAS_PASS="your_password"

# 挂载
bash scripts/mount_nas.sh
```

### 2. 配置 SentientOS

安装 SentientOS 后，配置其输出目录为本地路径，sync 脚本会自动推送到 NAS。

### 3. 运行桥接

```bash
# 状态检查
python workbuddy/memory_bridge.py

# 生成 WorkBuddy 上下文注入
python -c "from workbuddy.memory_bridge import MemoryBridge; MemoryBridge().generate_context_injection()"
```

### 4. 自动同步

GitHub Actions 每天凌晨 4 点自动运行，生成知识摘要并提交到仓库。

## WorkBuddy 集成

WorkBuddy 启动时自动读取 `knowledge/` 目录下的 SentientOS 摘要，将最近 3 天的知识注入对话上下文。

## 许可证

MIT
