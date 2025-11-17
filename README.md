# Claude Code 会话还原工具

这是一个用于还原 Claude Code 会话记录的 Python 工具，可以将 `.jsonl` 格式的原始对话数据转换为易于阅读的格式化文本。

## 功能特点

✨ **完整还原对话内容**
- 用户消息
- Claude 的回复
- 思考过程（Thinking）
- 工具调用及其结果
- Token 使用统计

🎯 **智能关联**
- 自动将 `tool_use` 和 `tool_result` 通过 ID 关联
- 按时间顺序重建完整对话流程
- 将同一个消息的多个内容块聚合在一起

📊 **多种输出格式**
- **文本格式（TXT）**：清晰的分隔线和标题，适合终端查看
- **Markdown格式（MD）**：结构化的markdown文档，适合GitHub/在线阅读
- Emoji 图标提升可读性
- 合理的内容截断和预览
- 时间戳格式化
- 自动保留原始markdown格式的内容

## 数据结构说明

### JSONL 文件格式

Claude Code 的会话数据以 JSONL（JSON Lines）格式存储，每一行是一个独立的 JSON 对象。主要类型包括：

```json
// 1. 队列操作（会被忽略）
{"type": "queue-operation", "operation": "enqueue", ...}

// 2. 用户消息
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [
      {"type": "text", "text": "用户的问题"}
    ]
  },
  "timestamp": "2025-11-13T16:23:46.008Z"
}

// 3. 助手消息（可能分多行，但共享同一个 message.id）
{
  "type": "assistant",
  "message": {
    "id": "msg_xxx",
    "role": "assistant",
    "content": [
      {"type": "thinking", "thinking": "思考内容"},
      {"type": "text", "text": "回复内容"},
      {"type": "tool_use", "id": "toolu_xxx", "name": "Read", "input": {...}}
    ],
    "usage": {"input_tokens": 10, "output_tokens": 436, ...}
  }
}

// 4. 工具结果（作为 user 类型）
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "tool_result",
        "tool_use_id": "toolu_xxx",  // 对应 tool_use 的 id
        "content": "工具执行结果"
      }
    ]
  }
}
```

### 关键关联

- **message.id**: 同一个助手消息的多个内容块（thinking、text、tool_use）会共享同一个 `message.id`
- **tool_use_id**: `tool_result` 通过 `tool_use_id` 字段引用对应的 `tool_use.id`，实现工具调用和结果的关联

## 安装要求

- Python 3.6+
- 无需额外依赖，仅使用 Python 标准库

## 使用方法

### 基本用法

```bash
# 使用默认文件名 case.jsonl，输出文本格式
python3 restore_chat.py

# 指定输入文件，输出文本格式
python3 restore_chat.py your_chat.jsonl

# 输出Markdown格式
python3 restore_chat.py --format markdown

# 使用短参数 -f 指定格式
python3 restore_chat.py -f md

# 指定输入文件并输出为Markdown格式
python3 restore_chat.py your_chat.jsonl --format markdown
```

### 输出格式

程序支持两种输出格式：

1. **文本格式（默认）**：生成 `*_restored.txt` 文件
   - 使用ASCII字符绘制的边框
   - 清晰的分隔线
   - 适合在终端或文本编辑器中查看

2. **Markdown格式**：生成 `*_restored.md` 文件
   - 标准的Markdown语法
   - 使用代码块包裹工具结果
   - 思考过程使用可折叠的 `<details>` 标签
   - 保留原始回复中的markdown格式
   - 适合在GitHub、在线markdown查看器或支持markdown的编辑器中查看

#### 示例输出 - 文本格式

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    Claude Code 会话还原                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝

================================================================================
👤 用户 [2025-11-13 16:23:46]
================================================================================
📂 The user opened the file /path/to/file.py
这是用户的问题...

================================================================================
🤖 Claude [2025-11-13 16:23:52]
📊 Tokens: 输入=10, 输出=436, 缓存读取=12447
================================================================================

💭 思考过程:
--------------------------------------------------------------------------------
  Claude 的思考内容...
--------------------------------------------------------------------------------

💬 回复:
--------------------------------------------------------------------------------
Claude 的回复内容...
--------------------------------------------------------------------------------

  🔧 工具调用: Read
  ID: toolu_xxx
  参数:
    file_path: /path/to/file.py

  📤 工具结果:
    文件内容...
```

#### 示例输出 - Markdown格式

```markdown
# Claude Code 会话还原

---

## 👤 用户 `2025-11-13 16:23:46`

📂 **打开文件**: `/path/to/file.py`

这是用户的问题...

---

## 🤖 Claude `2025-11-13 16:23:52`

📊 **Tokens**: 输入=10, 输出=436, 缓存读取=12447

### 💭 思考过程

<details>
<summary>展开思考过程</summary>

\`\`\`
Claude 的思考内容...
\`\`\`

</details>

### 💬 回复

Claude 的回复内容（保留原始markdown格式）...

#### 🔧 工具调用: `Read`

**ID**: `toolu_xxx`

**参数**:
\`\`\`json
{
  "file_path": "/path/to/file.py"
}
\`\`\`

#### 📤 工具结果:

\`\`\`
文件内容...
\`\`\`
```

## 文件说明

### 核心文件

- **`restore_chat.py`**: 主程序，包含会话还原的所有逻辑
- **`dev_plan.md`**: 开发规划和技术文档（中文）
- **`case.jsonl`**: 示例对话数据
- **`case_chat_snapshot.png`**: 会话示意图

### 生成文件

- **`case_restored.txt`**: 还原后的对话文本
- **`README.md`**: 本文档

## 技术架构

### 核心类: ChatRestorer

```python
class ChatRestorer:
    def __init__(self, jsonl_file: str)
        # 初始化，加载 JSONL 文件路径

    def load_data(self)
        # 加载 JSONL 数据，提取 tool_result 并建立索引

    def group_messages(self) -> List[Dict]
        # 将同一 message.id 的内容块聚合
        # 按时间排序，合并用户和助手消息

    def format_thinking(self, thinking_text: str) -> str
        # 格式化思考过程内容

    def format_tool_use(self, tool: Dict) -> str
        # 格式化工具调用，并关联对应的 tool_result

    def format_message(self, msg: Dict) -> str
        # 格式化单条消息（用户或助手）

    def restore(self) -> str
        # 主流程：还原完整会话
```

### 处理流程

1. **加载阶段**: 读取 JSONL 文件，建立 `tool_use_id -> tool_result` 的映射
2. **聚合阶段**: 将同一 `message.id` 的多个内容块合并成单个消息对象
3. **排序阶段**: 按时间戳对所有消息（用户+助手）排序
4. **格式化阶段**: 将每条消息渲染为友好的文本格式
5. **输出阶段**: 生成最终的 `.txt` 文件

## 设计亮点

### 1. 智能内容关联

程序自动处理以下关联：
- 同一个 `message.id` 的多个 JSONL 行（thinking、text、tool_use）
- `tool_use` 和 `tool_result` 的 ID 匹配（通过 `tool_use_id`）

### 2. 内容截断处理

对于过长的内容（如大型文件读取结果），程序会：
- 截断超过 500 字符的内容
- 显示前 20 行并标注剩余行数
- 保持输出的可读性

### 3. 鲁棒性设计

- 使用 `try-except` 处理 JSON 解析错误
- 跳过无效或不相关的行（如 `queue-operation`）
- 安全的时间戳格式化

### 4. 可扩展性

代码结构清晰，易于扩展：
- 添加新的内容类型处理
- 支持不同的输出格式（HTML、Markdown 等）
- 自定义格式化规则

## 应用场景

- 📚 **学习参考**: 回顾 Claude 的思考过程和问题解决方法
- 🔍 **问题排查**: 分析会话中的工具调用和错误
- 📊 **使用分析**: 统计 token 使用情况
- 📝 **文档记录**: 导出会话作为项目文档

## 与 dev_plan.md 的关系

本工具是根据 `dev_plan.md` 中的技术分析开发的：

- **数据源理解**: 基于文档中对 JSONL 格式的详细分析
- **架构选择**: 采用文档推荐的"独立脚本"架构（路径 1）
- **解析逻辑**: 实现了文档第 4 部分描述的会话重建算法
- **防御性编程**: 遵循文档第 5.3 节的健壮性策略

## 局限性

- 不支持从 SQLite 数据库（`__store.db`）读取元数据
- 不处理项目级别的组织（仅处理单个 JSONL 文件）

## 未来改进

- [ ] 支持从 `~/.claude/__store.db` 读取会话列表
- [ ] 添加交互式会话选择菜单
- [ ] 支持批量导出多个会话
- [x] 添加 Markdown 输出格式 ✅
- [ ] 添加 HTML 输出格式
- [ ] 支持配置文件自定义格式化规则
- [ ] 添加会话统计分析功能

## 许可证

本项目为教育和个人使用目的开发。

## 致谢

感谢 Claude Code 团队提供的强大工具，以及社区中分享的各种技术洞察。

---

**提示**: 如果你发现任何问题或有改进建议，欢迎提出 Issue 或贡献代码！
