

# **开发 Claude Code 对话导出脚本的技术架构与实现指南**

## **摘要**

本报告旨在为开发一个用于从 Visual Studio Code (VSCode) 导出 Claude Code 对话的自定义脚本提供一个详尽的技术蓝图。报告深入分析了 Claude Code 插件（anthropic.claude-code）在本地系统中的数据存储架构，通过逆向工程剖析了其使用的、无公开文档的数据格式，并评估了多种可行的开发架构。

分析表明，Claude Code 采用了一种“解耦”的存储策略，将其数据（包括一个中央 SQLite 数据库和一个 JSONL 格式的原始日志集合）存储在用户主目录下的 .claude/ 文件夹中 1。这一发现极大地简化了脚本的开发，使其摆脱了对 VSCode 扩展 API 的依赖。

本报告的最终目标是提供一个完整的、可操作的框架，使开发人员能够构建一个功能“完备”且“智能”的导出脚本。该脚本不仅能解析原始对话内容，还能利用中央数据库的元数据来智能地组织和检索会话，从而超越当前市面上大多数仅依赖文件系统扫描的工具。

---

## **第 1 部分：现状分析：Claude Code 导出工具的现有生态**

在着手开发新脚本之前，必须对现有的“最先进” (state-of-the-art) 工具进行全面评估。此举的目的不仅是了解现有解决方案，更是为了识别它们在功能或技术实现上的“技术鸿沟”，从而明确新脚本的核心价值主张。

### **1.1 范围界定：VSCode (Claude Code) 与 Web (claude.ai)**

首先必须明确一个关键区别：用户的请求针对的是“VSCode中的Claude Code对话”。这与从 Claude Web 界面（claude.ai）导出对话是两个完全不同的技术领域。

市面上存在一些用于导出 LLM 聊天内容的工具，例如 chat-export 3。然而，这是一个“浏览器扩展” (Browser extension)，其工作原理是抓取 Web DOM 或拦截网络请求。

这种方法对于我们的任务是完全无效的。VSCode 中的 Claude Code 是一个（或多个）在本地运行的进程，它将数据持久化到本地文件系统 1。因此，我们的脚本必须是一个**本地文件解析器**，而不是一个浏览器抓取器。任何针对网页的解决方案（如 3) 在此均不适用。

### **1.2 类别 1：命令行工具 (CLI)**

这是最接近用户“脚本”请求的类别。这些工具通常作为独立的二进制文件或通过包管理器（如 npm, pip）安装。

* **claude-conversation-extractor** 2：  
  * **技术栈**：Python。  
  * **数据源**：该工具的文档非常明确，它“自动在 \~/.claude/projects 中查找 Claude Code 日志” 2。它确认了这些日志是“Claude JSONL 文件” 2，并称其为 Claude Code 用来存储聊天的“无文档格式” 2。  
  * **功能**：提供交互式菜单、实时搜索和 \--all 批量备份。其关键功能是 \--detailed 标志，用于导出包含“工具调用、MCP 响应、终端输出和系统消息”的完整记录 2。  
* **claude-code-exporter** 4：  
  * **技术栈**：Node.js (npm)。  
  * **数据源**：文档相对模糊，提到了 \~/.claude 和 \~/.config/claude 两个路径 4。  
  * **功能**：支持 Markdown (-m) 和 JSON (-j) 输出，并能区分“完整对话” (-f)、仅用户提示 (-p) 或仅助手输出 (-o) 4。  
* **claude-code-log** 5：  
  * **技术栈**：Python。  
  * **数据源**：同样是解析 JSONL 文件 6。  
  * **功能**：此工具的独特之处在于其输出。它不仅是导出，更是将原始日志*渲染*为精美的 HTML 页面，其中包含“思考 token、工具输入和输出”等详细信息 6。其清晰的架构（parser.py, renderer.py, models.py）5 为我们构建新脚本提供了优秀的范本。

### **1.3 类别 2：VSCode 集成扩展**

这些工具在 VSCode 环境内部运行，提供 UI 交互。

* **claude-chats** 7：  
  * **核心功能**：此扩展并非用于“导出”，而是用于“管理”，特别是“重命名”对话。  
  * **关键发现**：它的工作方式极具启发性。它通过“修改 Claude Code 使用的实际 .jsonl 对话文件”来实现重命名 7。它会读取文件，找到“第一条用户消息”（Claude Code 将其用作标题），修改内容，然后写回文件 7。  
  * **推论**：这 100% 证实了 JSONL 文件是对话内容的“事实来源” (source of truth)，并且它们是可变的 (mutable)。  
* **Claude History Viewer** 8：  
  * **核心功能**：在 VSCode 的活动栏中提供一个 UI，用于查看、搜索和审查会话中的“文件变更” (diffs)。  
  * **关键发现**：该扩展的描述中明确提到了“强大的基于 SQLite 的搜索” (powerful SQLite-based search) 8。这是第一个强有力的证据，表明系统中存在一个 SQLite 数据库，并且它被用于*搜索和索引*。

### **1.4 类别 3：会话包装器 (Wrappers)**

* **specstory** 1：  
  * **核心功能**：这是一种完全不同的架构。它不是一个导出器，而是一个*包装器*。用户运行 specstory，该命令*反过来*启动 Claude Code 1。  
  * **数据源**：它在捕获会话时，将其保存到*自己*的目录中 (.specstory/history/) 1。  
  * **推论**：此工具不能用于导出*已经存在*的或*标准*的 Claude Code 日志。它是一个独立的日志记录系统，因此与我们的目标不符。

### **1.5 综合分析与“技术鸿沟”的识别**

通过分析上述工具，我们发现了一个明显的数据源不一致问题，即“双重数据源之谜”。

* **路径 1 (JSONL)**：绝大多数工具（如 2）和分析 2 都*只*关注 \~/.claude/projects/ 目录下的 JSONL 文件。  
* **路径 2 (SQLite)**：而其他来源（1）则惊人地声称 \~/.claude/\_\_store.db 文件才是“金蛋” (the golden egg)，其中“包含了一切” 1。Claude History Viewer 8 也证实了 SQLite 的存在。

这种分裂并非矛盾，而是一种*共生关系*。

1. JSONL 文件 2 是**原始的、非结构化的事务记录**。它们是*内容*。它们的文件名是难以理解的 UUID 11。  
2. \_\_store.db 1 是**索引**。它是*元数据*。这个数据库将 项目\_A 与 session\_guid\_123、session\_guid\_456 等关联起来。正是这个数据库，使得 Claude Code 的 UI 能够显示一个清晰的对话列表（而不是一堆 UUID）。

“技术鸿沟”的明确定义：  
现有的大多数 CLI 导出工具（如 claude-conversation-extractor）似乎都采用了一种“粗放” (dumb) 的方法：它们递归地扫描 \~/.claude/projects/ 目录，以查找所有 \*.jsonl 文件。这种方法虽然有效，但效率低下，并且完全丢失了来自数据库的丰富元数据（例如，可读的项目名称、用户在 UI 中设置的会话标题等）。  
对新脚本的启示：  
一个功能上更优越的脚本（即我们即将设计的脚本）不应该仅仅解析 JSONL 文件。它必须采用一种\*\*“智能”\*\*的方法：

1. **首先**，查询 \_\_store.db 以获取一个清晰的、被索引的会话列表（包含项目名、会话标题和 UUID）。  
2. **然后**，利用这些信息，精确地定位并解析*正确*的 JSONL 文件。

这是对现有工具生态的一个明确且价值显著的改进。

#### **表 1：现有导出工具的比较分析**

| 工具名称 | 类别 | 数据源（读取） | 输出格式 | 核心功能 |
| :---- | :---- | :---- | :---- | :---- |
| claude-conversation-extractor 2 | CLI (Python) | JSONL (\~/.claude/projects/) | Markdown, JSON, HTML | 交互式 CLI，直接解析 JSONL 文件，支持详细的工具调用导出。 |
| claude-code-exporter 4 | CLI (Node.js) | JSONL (从 \~/.claude 推断) | Markdown, JSON | 交互式 CLI，可过滤 prompt/output。 |
| claude-code-log 5 | CLI (Python) | JSONL (\~/.claude/projects/) | HTML | 将 JSONL 解析并渲染为高质量的 HTML 页面，用于审查。 |
| claude-chats 7 | VSCode 扩展 | JSONL (双向读/写) | (N/A) | 在 VSCode 内部*修改* JSONL 文件以重命名会话。 |
| Claude History Viewer 8 | VSCode 扩展 | JSONL 和 SQLite | (N/A) | 在 VSCode 中提供一个 UI，用于*搜索*（通过 SQLite）和*查看*（解析 JSONL）会话。 |
| specstory 1 | CLI 包装器 | 自有日志 (.specstory/history/) | Markdown | 包裹 Claude Code 进程，实时捕获对话并存入其*自有*的存储系统。 |
| chat-export 3 | 浏览器扩展 | Web DOM / XHR | Markdown, JSON, HTML | (范围不符) 导出*网站* (claude.ai) 上的对话。 |

---

## **第 2 部分：深入分析：Claude Code 的数据存储架构**

为了构建一个可靠的脚本，我们必须精确地绘制出 Claude Code 在文件系统上的“足迹”。这个过程揭示了一个与标准 VSCode 扩展截然不同的、刻意为之的架构。

### **2.1 标准：VSCode 扩展的常规数据存储（“障眼法”）**

要理解 Claude Code 的特殊性，首先必须了解“常规”的 VSCode 扩展是如何存储数据的。VSCode 扩展 API 提供了五种主要的数据存储机制 12：

1. workspaceState：特定于工作区的小型键值对。  
2. globalState：全局键值对。  
3. storageUri：特定于工作区的文件存储 URI。  
4. globalStorageUri：全局文件存储 URI。  
5. secrets：用于安全存储。

其中，globalState 14 是最常见的。当扩展使用 globalState 时，VSCode 会将这些数据统一存储在一个中央 SQLite 数据库中。这个文件的位置因平台而异：

* **Windows**: %APPDATA%\\Code\\User\\globalStorage\\state.vscdb 15  
* **macOS**: \~/Library/Application Support/Code/User/globalStorage/state.vscdb 14  
* **Linux**: \~/.config/Code/User/globalStorage/state.vscdb 15

这个 state.vscdb 数据库包含一个简单的 ItemTable (key, value) 表，其中 key 是扩展的唯一标识符（例如 publisher.extensionName），而 value 是该扩展存储的 JSON blob 16。

### **2.2 例外：Claude Code 的“独立”架构**

**关键的架构发现：Claude Code 采用了“解耦” (Decoupled) 架构。**

通过对所有证据的分析，我们得出一个明确的结论：Claude Code 扩展**完全没有使用**上述任何一个标准的 VSCode 存储机制。所有研究都一致且明确地指向一个自定义的、位于用户主目录顶层的文件夹：\~/.claude/ 1。

这种架构选择绝非偶然，其背后有深刻的技术考量：

1. **数据规模**：标准的 globalState 14 适用于存储小型键值对（如用户偏好设置）。而 Claude Code 的会话日志可能增长到数百兆字节 18，state.vscdb 根本不是为这种规模的“事务日志”设计的。  
2. **进程解耦**：这种设计强烈地支持了一个假设，即 VSCode 扩展（anthropic.claude-code）19 本身只是一个轻量级的“启动器” (launcher)。它可能只是为在后台运行的某个核心 claude-code CLI 进程 19 提供一个 UI 界面。这个后台进程执行所有繁重的工作（如 MCP 通信、文件系统 I/O），并将其日志写入*独立于 VSCode* 的 \~/.claude/ 目录中。  
3. **数据独立性**：通过在 VSCode 的生态系统*之外*创建 \~/.claude/，Anthropic 确保了其核心数据的生命周期与 VSCode 无关。即使用户卸载了 VSCode 扩展，数据仍然保留。

这对我们脚本的意义是什么？  
这是一个巨大的好消息。它极大地简化了我们的任务。我们不需要：

* 与任何 VSCode Extension API 24 交互。  
* 担心如何从 VSCode 的沙盒存储中读取数据。  
* 解析那个复杂的、共享的 state.vscdb 16。

我们的脚本是一个**纯粹的、简单的文件系统脚本**，它唯一的依赖就是能够访问用户的主目录。

### **2.3 绘制 \~/.claude/ 目录（真正的数据源）**

基于所有来源的综合分析，我们可以重建 \~/.claude/ 文件夹的内部结构：

**1\. 中央数据库（索引）**

* **文件**: \~/.claude/\_\_store.db 1  
* **格式**: SQLite 数据库 1  
* **目的**: 正如来源 1 所称的“金蛋”。它包含“一切”。我们推断这是元数据索引，存储了项目列表、项目路径、会话标题、会话 UUID 以及可能的“todos” 1。

**2\. 会话事务（内容）**

* **文件**: \~/.claude/projects/\<project-hash\>/chat\_\*.jsonl 2  
* **格式**: JSON Lines (JSONL) 2  
* **目的**: 包含每场会话的原始、完整事务记录。这包括用户输入、助手响应、系统消息、思考过程、工具使用 2 和 token 计数 10。

**3\. 杂项文件（噪音）**

* **目录**: \~/.claude/todos/ 1  
  * **目的**: 存储 Claude 为自己创建的任务（JSON 文件）。这对于*会话*导出可能是无关的噪音。  
* **文件**: \~/.claude.json 18  
  * **目的**: 这是一个问题文件。有报告称它会“持续累积”历史记录，导致性能问题 18。但更深入的分析 22 指出，这*并不是*主要的会话存储，而是一个“近期命令缓冲区”，并且存在一个 bug 导致其无限增长。

从噪音中过滤信号：  
一个健壮的导出脚本必须忽略 todos/ 目录和 \~/.claude.json 文件。唯一可靠的“事实来源”是 \_\_store.db（用于索引）和 projects/\*\*/\*.jsonl（用于内容）的组合读取。

#### **表 2：Claude Code 核心数据文件位置图**

| 操作系统 | 数据文件 | 标准路径 | 格式 | 目的 |
| :---- | :---- | :---- | :---- | :---- |
| Windows | **中央索引** | %USERPROFILE%\\.claude\\\_\_store.db | SQLite 3 | 会话元数据索引、项目列表、会话标题、UUID 1 |
| macOS | **中央索引** | \~/.claude/\_\_store.db | SQLite 3 | 会话元数据索引、项目列表、会话标题、UUID 1 |
| Linux | **中央索引** | \~/.claude/\_\_store.db | SQLite 3 | 会话元数据索引、项目列表、会话标题、UUID 1 |
| Windows | **会话内容** | %USERPROFILE%\\.claude\\projects\\\*\\chat\_\*.jsonl | JSON Lines (JSONL) | 原始会话事务记录（用户、助手、工具调用） 2 |
| macOS | **会话内容** | \~/.claude/projects/\*/chat\_\*.jsonl | JSON Lines (JSONL) | 原始会话事务记录（用户、助手、工具调用） 2 |
| Linux | **会话内容** | \~/.claude/projects/\*/chat\_\*.jsonl | JSON Lines (JSONL) | 原始会话事务记录（用户、助手、工具调用） 2 |
| 所有平台 | 任务 | \~/.claude/todos/\*.json | JSON | Claude 生成的“待办事项”。1 |
| 所有平台 | 缓冲区 | \~/.claude.json | JSON | 有 bug 的“近期命令”缓冲区。**不应**用于导出。 18 |

---

## **第 3 部分：技术实现：架构路径评估**

基于我们对 Claude Code “解耦”架构的理解，现在我们可以评估构建导出“脚本”的三种主要架构路径。

### **3.1 路径 1：独立脚本（Python/Node.js/Go）\[推荐\]**

* **架构**: 一个不依赖于 VSCode、在用户终端中直接运行的独立 CLI 脚本。  
* **逻辑**: 该脚本将实现我们在第 1.5 节中确定的“智能”方法：  
  1. 自动检测用户的主目录（Path.home()）。  
  2. 定位并使用 SQLite 驱动程序连接到 \~/.claude/\_\_store.db。  
  3. 执行 SQL 查询（参见第 4 部分），获取所有项目和会话的结构化列表（ProjectName, SessionTitle, SessionUUID, ProjectHash）。  
  4. （可选）在终端中显示一个交互式菜单（如 2），供用户选择要导出的会话。  
  5. 对于每个选定的会话，使用 ProjectHash 和 SessionUUID 精确构建 chat\_\*.jsonl 文件的路径。  
  6. 调用 JSONL 解析器（参见第 4 部分）来重建对话。  
  7. 将格式化（Markdown, JSON等）的输出写入当前工作目录。  
* **优势**:  
  1. **简单性与力量的结合**：此架构是完成任务所需的最简单、最直接的路径。  
  2. **可移植性**：脚本可以轻松地在任何安装了相应运行环境（Python/Node）的机器上运行，无论其是否安装了 VSCode。  
  3. **精确实现**：它完美地契合了用户的“脚本”请求。  
  4. **利用了核心发现**：它利用了第 2 部分的“解耦架构”发现，即我们*不需要* VSCode API。  
* **劣势**: 几乎没有。这是最纯粹的解决方案。

### **3.2 路径 2：集成式 VSCode 扩展**

* **架构**: 一个全新的、功能齐全的 VSCode 扩展，可能发布到 VSCode Marketplace 23。它会向命令面板（Ctrl+Shift+P）添加一个新命令，例如 "Claude: 导出所有对话" 12。  
* **逻辑**: 扩展的核心逻辑将**与路径 1 完全相同**。它*不会*使用 ExtensionContext.globalState 12（因为数据不在那里）。它将使用 Node.js 的 fs 和 sqlite3 模块，手动从 \~/.claude/ 目录读取文件，其方式与独立脚本一模一样。  
* **优势**:  
  1. **UI 集成**：可以在 VSCode 内部提供更美观的 UI（例如，使用 Webview 24 显示导出的内容）。  
* **劣势**:  
  1. **极高的复杂度**：开发者需要处理 VSCode API 24、package.json 中的 activationEvents、异步 API 调用、打包 (vsce package) 和发布 (vsce publish) 23 等一系列复杂问题。  
  2. **毫无必要的开销**：为了访问*已经*在文件系统上公开可用的数据，而引入整个 VSCode API 和扩展生命周期的复杂性，是一种架构上的浪费。

### **3.3 路径 3：混合方法（轻量级包装器）**

* **架构**: 一个轻量级的 VSCode 扩展，其本身*不包含*任何解析逻辑。它仅充当一个快捷方式。  
* **逻辑**: 该扩展在 VSCode 中注册一个命令。当用户触发该命令时，它只是在后台的 child\_process 中执行一个*已经存在*的 CLI 工具（例如，claude-extract \--all 2）。  
* **优势**:  
  1. **开发速度极快**：几行代码即可完成。  
* **劣势**:  
  1. **创建了外部依赖**：用户必须单独安装和维护该 CLI 工具。  
  2. **未解决核心问题**：它只是继承了被调用工具的*所有*技术缺陷，即它无法解决我们在第 1.5 节中确定的“技术鸿沟”（无法利用 \_\_store.db 进行智能索引）。

### **3.4 架构建议**

**明确推荐：路径 1（独立脚本）。**

**理由**：

1. **源于“解耦”架构**：第 2 部分的关键发现是，Claude 的数据存储是独立于 VSCode 的。因此，访问这些数据*不需要* VSCode API。一个简单的文件系统脚本是访问这些文件的最有效、最干净的工具。  
2. **满足用户请求**：用户要求提供一个“脚本”，而不是一个“扩展”。路径 1 精确地满足了这一要求。  
3. **规避复杂性**：路径 2（集成扩展）带来了巨大的、不必要的开发复杂性，而在数据访问方面*没有任何*技术优势。  
4. **解决技术鸿沟**：路径 1 允许我们专注于真正的问题——构建一个利用 \_\_store.db 和 JSONL 文件的“智能”解析器，这超越了路径 3 中那些“粗放”的现有工具。

---

## **第 4 部分：核心解剖：无文档数据格式的逆向工程**

这是本指南的核心。我们将详细说明如何读取和解释 Claude Code 的两个主要数据源。我们将使用 **Python** 作为示例语言，因为它内置了 sqlite3 和 json 库，使其成为此任务的理想选择 5。

### **4.1 探查 \_\_store.db (SQLite 索引)**

* **来源**: \~/.claude/\_\_store.db 1  
* **问题**: 这个数据库的模式（schema）是 100% 无文档的。网络上的某些信息 26 提到了 ai\_learning\_patterns 之类的表，但这具有误导性；它们描述的是 Claude *如何使用* SQLite 作为*工具*（通过 MCP）26，而不是 Claude *内部存储*的结构。  
* 发现模式的方法论:  
  由于模式未知，我们必须提供一种发现它的方法。最好的方法是在 VSCode 内部进行。  
  1. **安装工具**: 在 VSCode 中，安装 alexcvzz.vscode-sqlite 扩展 28 或 qwtel.sqlite-viewer 30。  
  2. **打开数据库**: 按 Ctrl+Shift+P 打开命令面板，运行 "SQLite: Open Database" 28。  
  3. **选择文件**: 导航到您的用户主目录，找到 .claude 文件夹，然后选择 \_\_store.db。  
  4. **检查模式**: "SQLITE EXPLORER" 视图将出现在侧边栏 28。展开它，您将看到数据库中所有的表。您可以右键单击任何表并选择 "Show Table" 29，或者创建一个新查询文件并运行 .schema 28 来查看所有表的 CREATE 语句。  
* 假设的查询与实现:  
  通过检查，我们很可能会发现像 projects 和 sessions 这样的表。projects 表可能包含项目名称和路径。sessions 表可能包含会话标题、创建时间戳以及一个指向 projects 的外键。它还必须包含一个唯一的 uuid，该 uuid 对应于 projects/ 目录中的 JSONL 文件名。  
  我们的 Python 脚本（路径 1）将执行一个（假设的）SQL 查询，如下所示：  
  Python  
  import sqlite3  
  import os

  CLAUDE\_HOME \= os.path.expanduser("\~/.claude")  
  DB\_PATH \= os.path.join(CLAUDE\_HOME, "\_\_store.db")

  def get\_sessions\_from\_db():  
      """  
      从 \_\_store.db 查询所有项目和会话元数据。  
      注意：表名和列名 (projects, sessions, name, title, uuid, project\_hash)   
      是基于逆向工程的假设。  
      """  
      try:  
          con \= sqlite3.connect(DB\_PATH)  
          cur \= con.cursor()

          \# 这个查询连接了两个假设的表：'projects' 和 'sessions'  
          \# 您需要根据您自己使用 SQLite Explorer 检查的结果来调整这个查询。  
          query \= """  
          SELECT   
              p.name AS project\_name,   
              p.hash AS project\_hash, \-- 假设这个 'hash' 对应于 'projects/' 下的目录名  
              s.uuid AS session\_uuid,   
              s.title AS session\_title,   
              s.created\_at AS timestamp  
          FROM sessions s  
          JOIN projects p ON s.project\_id \= p.id  
          ORDER BY p.name, s.created\_at DESC;  
          """

          res \= cur.execute(query)  
          \# 将结果作为字典列表返回，以便于访问  
          sessions \= \[dict(row) for row in res.fetchall()\]  
          con.close()  
          return sessions

      except sqlite3.Error as e:  
          print(f"Error querying SQLite database at {DB\_PATH}: {e}")  
          print("Please ensure the path is correct and the table/column names in the query are accurate.")  
          return

### **4.2 解析 chat\_\*.jsonl (会话内容)**

* **来源**: \~/.claude/projects/\<project-hash\>/chat\_{session\_uuid}.jsonl 2  
* **文件格式**: JSON Lines (JSONL)。这至关重要：它**不是一个 JSON 数组**。它是一个文本文件，其中**每一行**都是一个独立、完整、自包含的 JSON 对象 10。你必须逐行读取和解析它。  
* **文件标识**: 文件名（例如 c7bc33e6-dd71-409e-9a42-c45b27c6789f.jsonl 11）中的 UUID 正是我们在上一步中从 \_\_store.db 查询到的 session\_uuid。project-hash 也是如此。这就是“智能”脚本如何将索引与内容联系起来的。  
* **内容模式**: 来源 10 提供了一个完美的、具体的单行 JSON 示例，揭示了其嵌套结构。  
  * **顶层**: type (例如 "assistant"), timestamp, sessionId  
  * **嵌套 message**: message.id, message.role (例如 "assistant")  
  * **嵌套 usage**: message.usage.input\_tokens, message.usage.output\_tokens, cache\_creation\_input\_tokens, cache\_read\_input\_tokens 10  
* **内容类型**: 一个 JSONL 文件包含的远不止是简单的“用户”和“助手”消息。为了实现“详细”导出（如 2 中提到的），我们需要在一个循环中处理多种 type 或 role：  
  * 用户消息 (type: "user")  
  * 助手消息 (type: "assistant")  
  * 工具使用/调用 (type: "tool\_use")  
  * 工具结果/响应 (type: "tool\_result")  
  * 系统消息和思考过程（可能具有其他 type）  
  * “摘要条目” (Summary entries) 10：这些可能是 Claude 压缩旧对话的内部标记。对于面向用户的 Markdown 导出，这些条目可能应该被*过滤掉*。

#### **表 3：chat\_\*.jsonl 中单行 JSON 对象的重建模式（基于**

10

| 键路径 (Key Path) | 数据类型 | 描述 | 示例（来自 ） | 导出操作 |
| :---- | :---- | :---- | :---- | :---- |
| type | String | 日志条目的高级别类型。 | "assistant" | 用于路由解析器（例如，处理 "assistant" 消息）。 |
| timestamp | String | ISO 8601 时间戳。 | "2025-10-04T11:24:54.135Z" | 可选：添加到 Markdown 中以显示时间。 |
| sessionId | String | 该会话的唯一标识符。 | "c26cf239-…" | 验证这是否与我们从 DB 中获取的 session\_uuid 匹配。 |
| message.id | String | 该特定消息的唯一 ID。 | "msg\_01…" | \- |
| message.role | String | 消息的角色。 | "assistant" | 用于路由（"assistant", "user"）。 |
| message.content | String/Array | 消息的实际文本内容。 | (N/A) | **核心内容**。将其附加到 Markdown 输出。 |
| message.usage | Object | 包含 token 计数的嵌套对象。 | (Object) | \- |
| message.usage.input\_tokens | Integer | 发送给模型的输入 token 数。 | 7 | 累加到会话的总输入 token 计数。 |
| message.usage.output\_tokens | Integer | 模型生成的输出 token 数。 | 176 | 累加到会话的总输出 token 计数。 |
| message.usage.cache\_... | Integer | 与缓存相关的 token 计数。 | 464, 37687 | 累加到总数，用于高级分析。 |

### **4.3 会话重建算法**

现在，我们将所有部分组合成一个具体的算法，用于将单个 JSONL 文件转换为格式化的 Markdown 字符串。

Python

import json  
import os

\# (接续上文)  
PROJECTS\_PATH \= os.path.join(CLAUDE\_HOME, "projects")

def export\_session\_to\_markdown(project\_hash, session\_uuid):  
    """  
    读取单个 JSONL 文件，重建对话，并将其导出为 Markdown。  
      
    :param project\_hash: 从 \_\_store.db 获取的项目哈希 (目录名)  
    :param session\_uuid: 从 \_\_store.db 获取的会话 UUID (文件名)  
    :return: (markdown\_string, total\_input\_tokens, total\_output\_tokens)  
    """  
      
    \# 1\. 构造文件路径  
    file\_path \= os.path.join(PROJECTS\_PATH, project\_hash, f"chat\_{session\_uuid}.jsonl")  
      
    if not os.path.exists(file\_path):  
        print(f"Warning: File not found {file\_path}")  
        return "", 0, 0  
          
    output\_markdown \= ""  
    total\_input \= 0  
    total\_output \= 0  
      
    try:  
        with open(file\_path, 'r', encoding='utf-8') as f:  
            \# 2\. 逐行读取和解析  
            for line in f:  
                try:  
                    \# 3\. 积极的错误处理  
                    obj \= json.loads(line)  
                except json.JSONDecodeError:  
                    \# 可能会遇到损坏的行，如  中的错误报告所示  
                    output\_markdown \+= "\\n\\n\\n\\n"  
                    continue  
                  
                \# 4\. 基于 'message.role' 或 'type' 进行路由  
                role \= obj.get('message', {}).get('role')  
                msg\_type \= obj.get('type')  
                  
                content \= obj.get('message', {}).get('content', '')  
                  
                if role \== "user":  
                    output\_markdown \+= f"\> \*\*User:\*\*\\n{content}\\n\\n"  
                elif role \== "assistant":  
                    output\_markdown \+= f"\*\*Claude:\*\*\\n{content}\\n\\n"  
                elif msg\_type \== "tool\_use":  
                    \# 5\. 处理详细的工具调用 (如  所述)  
                    tool\_name \= obj.get('tool\_use', {}).get('name')  
                    tool\_input \= obj.get('tool\_use', {}).get('input')  
                    output\_markdown \+= f"\`\`\`json\\n\\n{json.dumps(tool\_input, indent=2)}\\n\`\`\`\\n\\n"  
                elif msg\_type \== "tool\_result":  
                    \# (可选) 也可以添加工具结果  
                    pass  
                elif msg\_type \== "summary":  
                    \# (可选) 过滤掉摘要条目 (如  所述)  
                    pass  
                      
                \# 6\. 聚合 Token (如  所述)  
                usage \= obj.get('message', {}).get('usage', {})  
                if usage:  
                    \# 使用.get() 确保鲁棒性  
                    total\_input \+= usage.get('input\_tokens', 0)  
                    total\_output \+= usage.get('output\_tokens', 0)

        return output\_markdown, total\_input, total\_output

    except Exception as e:  
        print(f"Error processing file {file\_path}: {e}")  
        return "", 0, 0

---

## **第 5 部分：建议与综合：健壮的导出脚本框架**

我们将所有分析合成为一个最终的、可操作的计划，用于构建用户所请求的脚本。

### **5.1 最终架构建议**

* **架构**: **路径 1：独立脚本**。如第 3 部分所述，这是最高效、最干净、最能利用我们架构发现的解决方案。  
* **语言**: **Python 3**。它内置了 sqlite3 和 json 库，使其成为此任务的理想选择，并且现有工具 2 已经证明了其可行性。

### **5.2 “智能”导出脚本的完整伪代码框架**

此框架将第 4.1 节（数据库查询）和第 4.3 节（JSONL 解析）组合成一个完整的主脚本。

Python

import sqlite3  
import json  
import os  
import re  
from pathlib import Path

\# \--- 1\. 常量和配置 (可配置的路径) \---  
CLAUDE\_HOME \= Path.home() / ".claude"  
DB\_PATH \= CLAUDE\_HOME / "\_\_store.db"  
PROJECTS\_PATH \= CLAUDE\_HOME / "projects"  
EXPORT\_DIR \= Path.cwd() / "claude\_exports"

\# \--- 2\. 数据库模块 (来自 4.1) \---  
def get\_sessions\_from\_db():  
    """从 \_\_store.db 查询所有项目和会话元数据。"""  
    if not DB\_PATH.exists():  
        print(f"Error: Database not found at {DB\_PATH}")  
        return  
          
    \# 假设的查询 \- 需要根据实际的 DB 模式进行验证  
    \# 注意：我们假设 'projects' 表有 'name' 和 'hash' 列  
    \# 'sessions' 表有 'uuid', 'title', 和 'project\_id' 列  
    QUERY \= """  
        SELECT   
            p.name AS project\_name,   
            p.hash AS project\_hash,  
            s.uuid AS session\_uuid,   
            s.title AS session\_title,   
            s.created\_at AS timestamp  
        FROM sessions s  
        JOIN projects p ON s.project\_id \= p.id  
        WHERE p.hash IS NOT NULL AND s.uuid IS NOT NULL  
        ORDER BY p.name, s.created\_at DESC;  
    """  
      
    sessions\_list \=  
    try:  
        con \= sqlite3.connect(DB\_PATH)  
        con.row\_factory \= sqlite3.Row \# 以字典形式访问列  
        cur \= con.cursor()  
          
        \# 数据库模式验证 (防御性编程)  
        cur.execute("SELECT name FROM sqlite\_master WHERE type='table' AND name='sessions';")  
        if not cur.fetchone():  
            print("Error: 'sessions' table not found in database. The schema may have changed.")  
            con.close()  
            return  
              
        cur.execute(QUERY)  
        sessions\_list \= \[dict(row) for row in cur.fetchall()\]  
        con.close()  
          
    except sqlite3.Error as e:  
        print(f"Database Error: {e}. Failed to query sessions.")  
        print("Tip: Use 'vscode-sqlite' to inspect the schema of \_\_store.db and fix the QUERY.")  
          
    return sessions\_list

\# \--- 3\. 解析器模块 (来自 4.3) \---  
def export\_session\_to\_markdown(project\_hash, session\_uuid):  
    """读取 JSONL，返回 (markdown\_string, input\_tokens, output\_tokens)。"""  
      
    file\_path \= PROJECTS\_PATH / project\_hash / f"chat\_{session\_uuid}.jsonl"  
      
    if not file\_path.exists():  
        return f"\# Error: File not found\\n{file\_path}", 0, 0  
          
    output\_md \= ""  
    total\_in, total\_out \= 0, 0  
      
    with open(file\_path, 'r', encoding='utf-8') as f:  
        for line\_num, line in enumerate(f):  
            try:  
                obj \= json.loads(line)  
            except json.JSONDecodeError:  
                output\_md \+= f"\\n\\n\\n\\n"  
                continue  
              
            \# (详细的路由逻辑，如 4.3 所示...)  
            role \= obj.get('message', {}).get('role')  
            content \= obj.get('message', {}).get('content', '')

            if role \== "user":  
                output\_md \+= f"\> \*\*User:\*\*\\n{content}\\n\\n"  
            elif role \== "assistant":  
                output\_md \+= f"\*\*Claude:\*\*\\n{content}\\n\\n"  
            \# (添加对 'tool\_use' 等的更多处理...)  
              
            \# 聚合 Token  
            usage \= obj.get('message', {}).get('usage', {})  
            if usage:  
                total\_in \+= usage.get('input\_tokens', 0)  
                total\_out \+= usage.get('output\_tokens', 0)  
                  
    return output\_md, total\_in, total\_out

\# \--- 4\. 实用工具 \---  
def sanitize\_filename(name):  
    """清理字符串，使其成为有效的文件名。"""  
    name \= re.sub(r'\[\<\>:"/\\\\|?\*\]', '\_', name)  
    return name\[:150\] \# 限制长度

\# \--- 5\. 主执行函数 \---  
def main():  
    print("Fetching Claude Code sessions from database...")  
    sessions \= get\_sessions\_from\_db()  
      
    if not sessions:  
        print("No sessions found. Exiting.")  
        return  
          
    print(f"Found {len(sessions)} sessions across all projects.")  
      
    \# (可选) 在此处实现一个交互式菜单    
    \# 来选择 'sessions' 列表中的特定会话。  
    \# 为简单起见，我们先导出所有内容。  
      
    EXPORT\_DIR.mkdir(exist\_ok=True)  
    print(f"Exporting all sessions to: {EXPORT\_DIR}")  
      
    all\_tokens\_in, all\_tokens\_out \= 0, 0  
      
    for session in sessions:  
        project\_name \= sanitize\_filename(session\['project\_name'\])  
        session\_title \= sanitize\_filename(session\['session\_title'\])  
          
        \# 智能的文件名  
        filename \= f"{project\_name} \- {session\_title}.md"  
          
        \# 创建特定于项目的子目录  
        project\_dir \= EXPORT\_DIR / project\_name  
        project\_dir.mkdir(exist\_ok=True)  
        export\_path \= project\_dir / filename  
          
        print(f"Exporting '{session\_title}' from '{project\_name}'...")  
          
        markdown, in\_tokens, out\_tokens \= export\_session\_to\_markdown(  
            session\['project\_hash'\],   
            session\['session\_uuid'\]  
        )  
          
        \# 写入元数据和内容  
        header \= f"\# {session\['session\_title'\]}\\n\\n"  
        header \+= f"\*\*Project:\*\* {session\['project\_name'\]}\\n"  
        header \+= f"\*\*Timestamp:\*\* {session\['timestamp'\]}\\n"  
        header \+= f"\*\*Tokens:\*\* Input: {in\_tokens}, Output: {out\_tokens}\\n"  
        header \+= f"---\\n\\n"  
          
        try:  
            with open(export\_path, 'w', encoding='utf-8') as f:  
                f.write(header \+ markdown)  
        except Exception as e:  
            print(f"Error writing file {export\_path}: {e}")  
              
        all\_tokens\_in \+= in\_tokens  
        all\_tokens\_out \+= out\_tokens  
          
    print("\\n--- Export Complete \---")  
    print(f"Total Sessions: {len(sessions)}")  
    print(f"Total Input Tokens: {all\_tokens\_in}")  
    print(f"Total Output Tokens: {all\_tokens\_out}")  
    print(f"Output Location: {EXPORT\_DIR}")

if \_\_name\_\_ \== "\_\_main\_\_":  
    main()

### **5.3 健壮性与未来维护策略**

**核心问题**：我们正在构建的脚本依赖于一个**完全无文档**的数据库模式和文件格式 2。在 Claude Code 的下一次更新中，Anthropic 可能会：

* 更改 \_\_store.db 的模式（重命名表或列）。  
* 更改 JSONL 对象的结构。  
* 将数据迁移到 \~/.claude/ 之外的位置。

任何这些更改都会立即使我们的脚本失效。

**防御性编码策略**：

1. **路径可配置**：如伪代码所示，所有路径（CLAUDE\_HOME, DB\_PATH）都应定义为脚本顶部的常量，而不是硬编码在函数中。  
2. **积极的错误处理**：  
   * JSONL 解析：**每一行** json.loads(line) 都**必须**封装在 try...except 块中。一个损坏的行（如 6 中报告的）不应该使整个导出过程崩溃。  
   * 字典访问：**每一个**嵌套的键访问都**必须**使用 .get('key', default\_value)（例如 obj.get('message', {}).get('usage', {})），以避免因缺少某个键（例如一个没有 usage 块的消息）而引发 KeyError。  
3. **数据库模式验证**：在执行主查询*之前*，脚本应该运行一个简单的“自检”查询（如伪代码中的 PRAGMA 或 sqlite\_master 查询）。它应该检查 sessions 表和关键列（uuid, title）是否存在。如果不存在，脚本应立即失败，并向用户显示一条清晰的错误消息，说明数据库模式可能已更改。  
4. **备份功能**：添加一个简单的命令行标志（例如 \--backup），该标志不执行任何解析，而是简单地创建整个 \~/.claude/ 目录的 zip 归档文件（灵感来自 claude-extract \--all 2）。这是在格式发生变化时保护用户数据的最后一道防线。

### **结论**

本报告提供了一个完整的技术蓝图，用于开发一个功能强大的 Claude Code 导出脚本。通过识别现有工具的“技术鸿沟”，我们确立了一个更优越的“智能”架构。该架构首先查询 \_\_store.db (索引) 以获取元数据，然后利用该元数据精确定位并解析 projects/\*\*/\*.jsonl (内容) 文件。

这种方法利用了 Claude Code 特有的“解耦”存储架构，从而使我们能够构建一个简单、独立（不依赖 VSCode）的脚本。所提供的伪代码和算法为解析这两种无文档的数据格式提供了坚实的基础。

遵循本指南的开发人员不仅能够创建一个满足其当前需求的脚本，而且还将拥有一套健壮的策略，以便在未来 Claude Code 更新导致数据格式演变时，能够快速诊断和维护该脚本。

#### **引用的著作**

1. Is there any way to get a history of my interactions with Claude Code ? : r/ClaudeAI \- Reddit, 访问时间为 十一月 14, 2025， [https://www.reddit.com/r/ClaudeAI/comments/1j5nh09/is\_there\_any\_way\_to\_get\_a\_history\_of\_my/](https://www.reddit.com/r/ClaudeAI/comments/1j5nh09/is_there_any_way_to_get_a_history_of_my/)  
2. ZeroSumQuant/claude-conversation-extractor: Extract ... \- GitHub, 访问时间为 十一月 14, 2025， [https://github.com/ZeroSumQuant/claude-conversation-extractor](https://github.com/ZeroSumQuant/claude-conversation-extractor)  
3. Trifall/chat-export: Browser extension that allows you to export chat conversations from the LLM sites ChatGPT and Claude to Markdown, XML, JSON, and HTML. \- GitHub, 访问时间为 十一月 14, 2025， [https://github.com/Trifall/chat-export](https://github.com/Trifall/chat-export)  
4. developerisnow/claude-code-exporter: Export and ... \- GitHub, 访问时间为 十一月 14, 2025， [https://github.com/developerisnow/claude-code-exporter](https://github.com/developerisnow/claude-code-exporter)  
5. daaain/claude-code-log: A Python CLI tool that converts Claude Code transcript JSONL files into readable HTML format. \- GitHub, 访问时间为 十一月 14, 2025， [https://github.com/daaain/claude-code-log](https://github.com/daaain/claude-code-log)  
6. I created a Python CLI tool to parse Claude Code's local transcripts into HTML pages, 访问时间为 十一月 14, 2025， [https://www.reddit.com/r/ClaudeAI/comments/1lcp8bt/i\_created\_a\_python\_cli\_tool\_to\_parse\_claude\_codes/](https://www.reddit.com/r/ClaudeAI/comments/1lcp8bt/i_created_a_python_cli_tool_to_parse_claude_codes/)  
7. Claude Chats \- Visual Studio Marketplace, 访问时间为 十一月 14, 2025， [https://marketplace.visualstudio.com/items?itemName=AlexZanfir.claude-chats](https://marketplace.visualstudio.com/items?itemName=AlexZanfir.claude-chats)  
8. Claude Code Assist \- Chat History & Diff Viewer | Usage Viewer \- Visual Studio Marketplace, 访问时间为 十一月 14, 2025， [https://marketplace.visualstudio.com/items?itemName=agsoft.claude-history-viewer](https://marketplace.visualstudio.com/items?itemName=agsoft.claude-history-viewer)  
9. How can i save claude codes conversation for future references? : r/ClaudeAI \- Reddit, 访问时间为 十一月 14, 2025， [https://www.reddit.com/r/ClaudeAI/comments/1l33v4t/how\_can\_i\_save\_claude\_codes\_conversation\_for/](https://www.reddit.com/r/ClaudeAI/comments/1l33v4t/how_can_i_save_claude_codes_conversation_for/)  
10. How to Track Claude Token Usage in Real Time with a VS Code Extension \- Yahya Shareef, 访问时间为 十一月 14, 2025， [https://yahya-shareef.medium.com/how-to-track-claude-token-usage-in-real-time-with-a-vs-code-extension-a596b40712c2](https://yahya-shareef.medium.com/how-to-track-claude-token-usage-in-real-time-with-a-vs-code-extension-a596b40712c2)  
11. Conversation history shows duplicate 'Warmup' titles and loads wrong conversations · Issue \#9668 · anthropics/claude-code \- GitHub, 访问时间为 十一月 14, 2025， [https://github.com/anthropics/claude-code/issues/9668](https://github.com/anthropics/claude-code/issues/9668)  
12. Common Capabilities | Visual Studio Code Extension API, 访问时间为 十一月 14, 2025， [https://code.visualstudio.com/api/extension-capabilities/common-capabilities](https://code.visualstudio.com/api/extension-capabilities/common-capabilities)  
13. Does the VSCode extension API allow an extension to store data or maintain any state?, 访问时间为 十一月 14, 2025， [https://stackoverflow.com/questions/50775276/does-the-vscode-extension-api-allow-an-extension-to-store-data-or-maintain-any-s](https://stackoverflow.com/questions/50775276/does-the-vscode-extension-api-allow-an-extension-to-store-data-or-maintain-any-s)  
14. VS Code Extension Storage Explained: The What, Where, and How | by Krithika Nithyanandam | Medium, 访问时间为 十一月 14, 2025， [https://medium.com/@krithikanithyanandam/vs-code-extension-storage-explained-the-what-where-and-how-3a0846a632ea](https://medium.com/@krithikanithyanandam/vs-code-extension-storage-explained-the-what-where-and-how-3a0846a632ea)  
15. How does, where does, VSCode mark an extension as disabled? \- Reddit, 访问时间为 十一月 14, 2025， [https://www.reddit.com/r/vscode/comments/hxv68q/how\_does\_where\_does\_vscode\_mark\_an\_extension\_as/](https://www.reddit.com/r/vscode/comments/hxv68q/how_does_where_does_vscode_mark_an_extension_as/)  
16. Work out how to manually clear VS Code's Memento/globalState storage \#21 \- GitHub, 访问时间为 十一月 14, 2025， [https://github.com/mattreduce/venus/issues/21](https://github.com/mattreduce/venus/issues/21)  
17. Exploring VS Code's Global State \- mattreduce, 访问时间为 十一月 14, 2025， [https://mattreduce.com/posts/vscode-global-state/](https://mattreduce.com/posts/vscode-global-state/)  
18. History accumulation in .claude.json causes performance issues and storage bloat \#5024, 访问时间为 十一月 14, 2025， [https://github.com/anthropics/claude-code/issues/5024](https://github.com/anthropics/claude-code/issues/5024)  
19. How To Install Claude Code Extension in VS Code \- YouTube, 访问时间为 十一月 14, 2025， [https://www.youtube.com/watch?v=0FmT0uasKWw](https://www.youtube.com/watch?v=0FmT0uasKWw)  
20. How I use Claude Code (+ my best tips) \- Builder.io, 访问时间为 十一月 14, 2025， [https://www.builder.io/blog/claude-code](https://www.builder.io/blog/claude-code)  
21. Beautiful Claude Code Chat Interface for VS Code \- Visual Studio Marketplace, 访问时间为 十一月 14, 2025， [https://marketplace.visualstudio.com/items?itemName=AndrePimenta.claude-code-chat](https://marketplace.visualstudio.com/items?itemName=AndrePimenta.claude-code-chat)  
22. Entire conversation history in .claude.json : r/ClaudeAI \- Reddit, 访问时间为 十一月 14, 2025， [https://www.reddit.com/r/ClaudeAI/comments/1moe4nq/entire\_conversation\_history\_in\_claudejson/](https://www.reddit.com/r/ClaudeAI/comments/1moe4nq/entire_conversation_history_in_claudejson/)  
23. Publishing Extensions \- Visual Studio Code, 访问时间为 十一月 14, 2025， [https://code.visualstudio.com/api/working-with-extensions/publishing-extension](https://code.visualstudio.com/api/working-with-extensions/publishing-extension)  
24. Extension API \- Visual Studio Code, 访问时间为 十一月 14, 2025， [https://code.visualstudio.com/api](https://code.visualstudio.com/api)  
25. VS Code API | Visual Studio Code Extension API, 访问时间为 十一月 14, 2025， [https://code.visualstudio.com/api/references/vscode-api](https://code.visualstudio.com/api/references/vscode-api)  
26. Use SQLite instead of markdown files to give Claude Code more enhanced memory. : r/ClaudeAI \- Reddit, 访问时间为 十一月 14, 2025， [https://www.reddit.com/r/ClaudeAI/comments/1ltkm6c/use\_sqlite\_instead\_of\_markdown\_files\_to\_give/](https://www.reddit.com/r/ClaudeAI/comments/1ltkm6c/use_sqlite_instead_of_markdown_files_to_give/)  
27. Claude Can Use Your SQLite Database \- YouTube, 访问时间为 十一月 14, 2025， [https://www.youtube.com/watch?v=wxCCzo9dGj0](https://www.youtube.com/watch?v=wxCCzo9dGj0)  
28. vscode-sqlite \- Visual Studio Marketplace, 访问时间为 十一月 14, 2025， [https://marketplace.visualstudio.com/items?itemName=alexcvzz.vscode-sqlite](https://marketplace.visualstudio.com/items?itemName=alexcvzz.vscode-sqlite)  
29. How to see a SQLite database content with Visual Studio Code \[closed\] \- Stack Overflow, 访问时间为 十一月 14, 2025， [https://stackoverflow.com/questions/40993895/how-to-see-a-sqlite-database-content-with-visual-studio-code](https://stackoverflow.com/questions/40993895/how-to-see-a-sqlite-database-content-with-visual-studio-code)  
30. View SQLite Databases in VS Code INSTANTLY | Stop Using SQLite Browser \- YouTube, 访问时间为 十一月 14, 2025， [https://www.youtube.com/watch?v=8lQRZ0vSIJQ](https://www.youtube.com/watch?v=8lQRZ0vSIJQ)  
31. Adding a VS-Code Extension to view SQLite Database (generated by SQLAlchemy), 访问时间为 十一月 14, 2025， [https://www.youtube.com/watch?v=R3Cq4QDzFEY](https://www.youtube.com/watch?v=R3Cq4QDzFEY)