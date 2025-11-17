#!/usr/bin/env python3
"""
Claude Code 会话还原程序
从 case.jsonl 还原完整的对话，包括 thinking、tool 调用和结果
支持文本和Markdown格式输出
"""

import json
import sys
import argparse
import os
import html as html_module
import re
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime


class ChatRestorer:
    def __init__(self, jsonl_file: str, output_format: str = 'txt'):
        self.jsonl_file = jsonl_file
        self.output_format = output_format  # 'txt' or 'markdown'
        self.messages = []  # 存储所有消息
        self.tool_results = {}  # 存储tool_result，以tool_use_id为key

    def load_data(self):
        """加载JSONL数据"""
        with open(self.jsonl_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    obj = json.loads(line.strip())
                    # 跳过queue-operation
                    if obj.get('type') in ['queue-operation']:
                        continue

                    # 收集tool_result
                    if obj.get('type') == 'user' and obj.get('message'):
                        content = obj['message'].get('content', [])
                        for item in content:
                            if item.get('type') == 'tool_result':
                                tool_use_id = item.get('tool_use_id')
                                if tool_use_id:
                                    self.tool_results[tool_use_id] = {
                                        'content': item.get('content', ''),
                                        'timestamp': obj.get('timestamp')
                                    }

                    self.messages.append(obj)
                except json.JSONDecodeError as e:
                    print(f"警告: 第 {line_num} 行JSON解析失败: {e}", file=sys.stderr)
                    continue

    def group_messages(self) -> List[Dict[str, Any]]:
        """
        将消息按message.id分组聚合
        返回聚合后的消息列表
        """
        grouped = {}
        user_messages = []

        for msg in self.messages:
            msg_type = msg.get('type')
            timestamp = msg.get('timestamp', '')

            if msg_type == 'user':
                # 用户消息（非tool_result）
                content = msg.get('message', {}).get('content', [])
                user_content = [c for c in content if c.get('type') != 'tool_result']
                if user_content:
                    user_messages.append({
                        'role': 'user',
                        'timestamp': timestamp,
                        'content': user_content,
                        'raw': msg
                    })

            elif msg_type == 'assistant':
                message = msg.get('message', {})
                msg_id = message.get('id')

                if msg_id:
                    if msg_id not in grouped:
                        grouped[msg_id] = {
                            'role': 'assistant',
                            'id': msg_id,
                            'timestamp': timestamp,
                            'content': [],
                            'usage': message.get('usage', {}),
                            'raw': msg
                        }

                    # 添加内容到该消息
                    content = message.get('content', [])
                    grouped[msg_id]['content'].extend(content)

        # 按时间排序并合并用户和助手消息
        all_messages = list(grouped.values()) + user_messages
        all_messages.sort(key=lambda x: x.get('timestamp', ''))

        return all_messages

    def format_thinking(self, thinking_text: str) -> str:
        """格式化thinking内容"""
        lines = thinking_text.split('\n')
        formatted = []
        for line in lines:
            if line.strip():
                formatted.append(f"  {line}")
        return '\n'.join(formatted)

    def format_tool_use(self, tool: Dict[str, Any]) -> str:
        """格式化tool_use内容"""
        tool_name = tool.get('name', 'Unknown')
        tool_id = tool.get('id', '')
        tool_input = tool.get('input', {})

        # 格式化输入参数
        params = []
        for key, value in tool_input.items():
            if isinstance(value, str) and len(value) > 100:
                value = value[:100] + '...'
            params.append(f"    {key}: {value}")

        result = [
            f"  🔧 工具调用: {tool_name}",
            f"  ID: {tool_id}",
        ]

        if params:
            result.append("  参数:")
            result.extend(params)

        # 查找对应的tool_result
        tool_result = self.tool_results.get(tool_id)
        if tool_result:
            result.append("\n  📤 工具结果:")
            content = tool_result['content']
            # 如果内容太长，截断显示
            if len(content) > 500:
                lines = content.split('\n')
                if len(lines) > 20:
                    preview = '\n'.join(lines[:20])
                    result.append(f"    {preview}")
                    result.append(f"    ... (还有 {len(lines) - 20} 行)")
                else:
                    result.append(f"    {content[:500]}...")
            else:
                # 添加缩进
                for line in content.split('\n'):
                    result.append(f"    {line}")

        return '\n'.join(result)

    def format_message(self, msg: Dict[str, Any]) -> str:
        """格式化单条消息"""
        role = msg.get('role', 'unknown')
        timestamp = msg.get('timestamp', '')
        content = msg.get('content', [])

        # 格式化时间戳
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            time_str = timestamp

        lines = []

        if role == 'user':
            lines.append("=" * 80)
            lines.append(f"👤 用户 [{time_str}]")
            lines.append("=" * 80)

            for item in content:
                item_type = item.get('type')
                if item_type == 'text':
                    text = item.get('text', '')
                    # 处理特殊标记
                    if '<ide_opened_file>' in text:
                        lines.append("📂 " + text.replace('<ide_opened_file>', '').replace('</ide_opened_file>', '').strip())
                    else:
                        lines.append(text)

        elif role == 'assistant':
            lines.append("=" * 80)
            lines.append(f"🤖 Claude [{time_str}]")

            # 显示token使用情况
            usage = msg.get('usage', {})
            if usage:
                input_tokens = usage.get('input_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)
                cache_read = usage.get('cache_read_input_tokens', 0)
                lines.append(f"📊 Tokens: 输入={input_tokens}, 输出={output_tokens}, 缓存读取={cache_read}")

            lines.append("=" * 80)

            # 按顺序处理内容
            for item in content:
                item_type = item.get('type')

                if item_type == 'thinking':
                    lines.append("\n💭 思考过程:")
                    lines.append("-" * 80)
                    thinking_text = item.get('thinking', '')
                    lines.append(self.format_thinking(thinking_text))
                    lines.append("-" * 80)

                elif item_type == 'text':
                    lines.append("\n💬 回复:")
                    lines.append("-" * 80)
                    lines.append(item.get('text', ''))
                    lines.append("-" * 80)

                elif item_type == 'tool_use':
                    lines.append("\n" + self.format_tool_use(item))

        return '\n'.join(lines)

    def format_thinking_markdown(self, thinking_text: str) -> str:
        """格式化thinking内容为Markdown"""
        # 保留原始的markdown格式
        return thinking_text

    def format_tool_use_markdown(self, tool: Dict[str, Any]) -> str:
        """格式化tool_use内容为Markdown"""
        tool_name = tool.get('name', 'Unknown')
        tool_id = tool.get('id', '')
        tool_input = tool.get('input', {})

        result = [
            f"#### 🔧 工具调用: `{tool_name}`",
            f"",
            f"**ID**: `{tool_id}`",
            f""
        ]

        # 格式化输入参数
        if tool_input:
            result.append("**参数**:")
            result.append("```json")
            result.append(json.dumps(tool_input, indent=2, ensure_ascii=False))
            result.append("```")
            result.append("")

        # 查找对应的tool_result
        tool_result = self.tool_results.get(tool_id)
        if tool_result:
            result.append("#### 📤 工具结果:")
            result.append("")
            content = tool_result['content']

            # 如果内容太长，截断显示
            if len(content) > 1000:
                lines = content.split('\n')
                if len(lines) > 30:
                    preview = '\n'.join(lines[:30])
                    result.append("```")
                    result.append(preview)
                    result.append("```")
                    result.append(f"")
                    result.append(f"*... (还有 {len(lines) - 30} 行)*")
                else:
                    result.append("```")
                    result.append(content[:1000] + "...")
                    result.append("```")
            else:
                # 保留markdown格式
                # 检查是否已经是代码块
                if content.strip().startswith('```'):
                    result.append(content)
                else:
                    result.append("```")
                    result.append(content)
                    result.append("```")
            result.append("")

        return '\n'.join(result)

    def format_message_markdown(self, msg: Dict[str, Any]) -> str:
        """格式化单条消息为Markdown"""
        role = msg.get('role', 'unknown')
        timestamp = msg.get('timestamp', '')
        content = msg.get('content', [])

        # 格式化时间戳
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            time_str = timestamp

        lines = []

        if role == 'user':
            lines.append("---")
            lines.append("")
            lines.append(f"## 👤 用户 `{time_str}`")
            lines.append("")

            for item in content:
                item_type = item.get('type')
                if item_type == 'text':
                    text = item.get('text', '')
                    # 处理特殊标记
                    if '<ide_opened_file>' in text:
                        file_path = text.replace('<ide_opened_file>', '').replace('</ide_opened_file>', '').strip()
                        lines.append(f"📂 **打开文件**: `{file_path}`")
                    else:
                        # 保留原始的markdown格式
                        lines.append(text)
                lines.append("")

        elif role == 'assistant':
            lines.append("---")
            lines.append("")
            lines.append(f"## 🤖 Claude `{time_str}`")
            lines.append("")

            # 显示token使用情况
            usage = msg.get('usage', {})
            if usage:
                input_tokens = usage.get('input_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)
                cache_read = usage.get('cache_read_input_tokens', 0)
                lines.append(f"📊 **Tokens**: 输入={input_tokens}, 输出={output_tokens}, 缓存读取={cache_read}")
                lines.append("")

            # 按顺序处理内容
            for item in content:
                item_type = item.get('type')

                if item_type == 'thinking':
                    lines.append("### 💭 思考过程")
                    lines.append("")
                    lines.append("<details>")
                    lines.append("<summary>展开思考过程</summary>")
                    lines.append("")
                    thinking_text = item.get('thinking', '')
                    lines.append("```")
                    lines.append(self.format_thinking_markdown(thinking_text))
                    lines.append("```")
                    lines.append("")
                    lines.append("</details>")
                    lines.append("")

                elif item_type == 'text':
                    lines.append("### 💬 回复")
                    lines.append("")
                    # 保留原始的markdown格式
                    lines.append(item.get('text', ''))
                    lines.append("")

                elif item_type == 'tool_use':
                    lines.append(self.format_tool_use_markdown(item))

        return '\n'.join(lines)

    def restore(self) -> str:
        """还原完整会话"""
        self.load_data()
        grouped_messages = self.group_messages()

        if self.output_format == 'markdown':
            return self._restore_markdown(grouped_messages)
        elif self.output_format == 'html':
            return self._restore_html(grouped_messages)
        else:
            return self._restore_text(grouped_messages)

    def _restore_text(self, grouped_messages: List[Dict[str, Any]]) -> str:
        """以文本格式还原会话"""
        output = []
        output.append("╔" + "═" * 78 + "╗")
        output.append("║" + " " * 20 + "Claude Code 会话还原" + " " * 38 + "║")
        output.append("╚" + "═" * 78 + "╝")
        output.append("")

        for i, msg in enumerate(grouped_messages, 1):
            output.append(self.format_message(msg))
            output.append("")  # 空行分隔

        output.append("\n")
        output.append("╔" + "═" * 78 + "╗")
        output.append("║" + " " * 30 + "会话结束" + " " * 38 + "║")
        output.append("╚" + "═" * 78 + "╝")

        return '\n'.join(output)

    def _restore_markdown(self, grouped_messages: List[Dict[str, Any]]) -> str:
        """以Markdown格式还原会话"""
        output = []
        output.append("# Claude Code 会话还原")
        output.append("")

        for i, msg in enumerate(grouped_messages, 1):
            output.append(self.format_message_markdown(msg))
            output.append("")  # 空行分隔

        output.append("---")
        output.append("")
        output.append("**会话结束**")

        return '\n'.join(output)

    def _markdown_to_html(self, markdown_text: str) -> str:
        """简单的Markdown到HTML转换"""
        if not markdown_text:
            return ""

        # HTML转义
        html = html_module.escape(markdown_text)

        # 代码块（三个反引号）- 需要先处理，避免内部内容被转换
        # 使用特殊字符作为占位符，避免被markdown规则匹配（如__会被识别为粗体）
        code_blocks = []
        def save_code_block(match):
            lang = match.group(1) or ''
            code = match.group(2)
            placeholder = f'◆CODEBLOCK§{len(code_blocks)}◆'
            code_blocks.append(f'<pre><code class="language-{lang}">{code}</code></pre>')
            return placeholder
        html = re.sub(r'```(\w*)\n(.*?)```', save_code_block, html, flags=re.DOTALL)

        # 行内代码（单个反引号）- 也需要保护起来
        inline_codes = []
        def save_inline_code(match):
            code = match.group(1)
            placeholder = f'◇INLINECODE§{len(inline_codes)}◇'
            inline_codes.append(f'<code>{code}</code>')
            return placeholder
        html = re.sub(r'`([^`]+)`', save_inline_code, html)

        # 粗体（需要处理嵌套）
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'__(.+?)__', r'<strong>\1</strong>', html)

        # 斜体
        html = re.sub(r'\*([^\*\s][^\*]*[^\*\s])\*', r'<em>\1</em>', html)
        html = re.sub(r'_([^_\s][^_]*[^_\s])_', r'<em>\1</em>', html)

        # 标题
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # 链接
        html = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', html)

        # 无序列表
        def replace_list(match):
            items = match.group(0)
            items_html = re.sub(r'^[-*+] (.+)$', r'  <li>\1</li>', items, flags=re.MULTILINE)
            return f'<ul>\n{items_html}\n</ul>'
        html = re.sub(r'(?:^[-*+] .+$\n?)+', replace_list, html, flags=re.MULTILINE)

        # 有序列表
        def replace_ordered_list(match):
            items = match.group(0)
            items_html = re.sub(r'^\d+\. (.+)$', r'  <li>\1</li>', items, flags=re.MULTILINE)
            return f'<ol>\n{items_html}\n</ol>'
        html = re.sub(r'(?:^\d+\. .+$\n?)+', replace_ordered_list, html, flags=re.MULTILINE)

        # 段落处理：空行分隔的段落（在恢复代码块之前处理，避免代码块被影响）
        paragraphs = html.split('\n\n')
        result_paragraphs = []
        for para in paragraphs:
            para = para.strip()
            if para:
                # 如果包含代码块占位符，直接添加不处理
                if '◆CODEBLOCK§' in para or para.startswith(('<h', '<ul>', '<ol>')):
                    result_paragraphs.append(para)
                else:
                    # 普通段落，将单个换行转为<br>
                    para = para.replace('\n', '<br>\n')
                    result_paragraphs.append(f'<p>{para}</p>')

        html = '\n'.join(result_paragraphs)

        # 恢复代码块（在段落处理之后，避免代码块内容被段落处理影响）
        for i, code_block in enumerate(code_blocks):
            html = html.replace(f'◆CODEBLOCK§{i}◆', code_block)

        # 恢复行内代码
        for i, inline_code in enumerate(inline_codes):
            html = html.replace(f'◇INLINECODE§{i}◇', inline_code)

        return html

    def _get_html_css(self) -> str:
        """获取HTML的CSS样式"""
        return """
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
                             'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;
                background: #1a1a1a;
                color: #e0e0e0;
                line-height: 1.6;
                padding: 20px;
            }

            .container {
                max-width: 900px;
                margin: 0 auto;
                background: #2a2a2a;
                border-radius: 12px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
                overflow: hidden;
            }

            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 30px;
                text-align: center;
                color: white;
            }

            .header h1 {
                font-size: 28px;
                font-weight: 600;
                margin-bottom: 5px;
            }

            .header .subtitle {
                opacity: 0.9;
                font-size: 14px;
            }

            .messages {
                padding: 20px;
            }

            .message {
                margin-bottom: 24px;
                animation: fadeIn 0.3s ease-in;
                border-radius: 8px;
                overflow: hidden;
            }

            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }

            .message-header {
                display: flex;
                align-items: center;
                margin-bottom: 12px;
                padding: 12px;
                border-bottom: 2px solid #3a3a3a;
                cursor: pointer;
                user-select: none;
                transition: background-color 0.2s;
            }

            .message-header:hover {
                background-color: rgba(255, 255, 255, 0.05);
            }

            .message.collapsed .message-content {
                display: none;
            }

            .message.collapsed .message-header {
                margin-bottom: 0;
            }

            .message-icon {
                font-size: 24px;
                margin-right: 10px;
            }

            .message-meta {
                flex: 1;
            }

            .message-role {
                font-weight: 600;
                font-size: 16px;
                color: #fff;
            }

            .message-timestamp {
                font-size: 12px;
                color: #888;
                margin-left: 12px;
            }

            .message-tokens {
                font-size: 12px;
                color: #888;
                display: flex;
                gap: 12px;
                margin-top: 4px;
            }

            .token-item {
                display: inline-block;
            }

            .message-content {
                padding-left: 34px;
            }

            .thinking-section {
                background: #3a2a4a;
                border-left: 4px solid #764ba2;
                padding: 16px;
                margin: 12px 0;
                border-radius: 6px;
            }

            .thinking-header {
                color: #b794f4;
                font-weight: 600;
                margin-bottom: 8px;
                cursor: pointer;
                user-select: none;
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .thinking-header:hover {
                color: #d6bcfa;
            }

            .collapse-icon {
                font-size: 12px;
                transition: transform 0.2s;
            }

            .collapsed .collapse-icon {
                transform: rotate(-90deg);
            }

            .thinking-content {
                color: #c4b5f7;
                font-size: 14px;
                white-space: pre-wrap;
                font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
                line-height: 1.5;
                max-height: 500px;
                overflow-y: auto;
            }

            .thinking-content.hidden {
                display: none;
            }

            .text-section {
                margin: 12px 0;
                color: #e0e0e0;
                line-height: 1.7;
            }

            .text-section.highlight {
                background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
                border-left: 4px solid #667eea;
                padding: 16px;
                border-radius: 6px;
            }

            .text-section h1 {
                font-size: 24px;
                margin-top: 20px;
                margin-bottom: 12px;
                color: #fff;
                font-weight: 600;
            }

            .text-section h2 {
                font-size: 20px;
                margin-top: 16px;
                margin-bottom: 10px;
                color: #fff;
                font-weight: 600;
            }

            .text-section h3 {
                font-size: 18px;
                margin-top: 14px;
                margin-bottom: 8px;
                color: #fff;
                font-weight: 600;
            }

            .text-section code {
                background: #3a3a3a;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
                font-size: 13px;
                color: #f78c6c;
            }

            .text-section pre {
                background: #0d1117;
                padding: 16px;
                border-radius: 8px;
                overflow-x: auto;
                margin: 12px 0;
                border: 1px solid #30363d;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
            }

            .text-section pre code {
                background: none;
                padding: 0;
                color: #e0e0e0;
                font-family: 'Monaco', 'Menlo', 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.6;
                display: block;
            }

            /* 优化highlight.js的代码高亮显示 */
            .text-section pre code.hljs {
                background: transparent;
                padding: 0;
            }

            .text-section a {
                color: #667eea;
                text-decoration: none;
                border-bottom: 1px solid transparent;
                transition: border-color 0.2s;
            }

            .text-section a:hover {
                border-bottom-color: #667eea;
            }

            .text-section ul, .text-section ol {
                margin: 12px 0;
                padding-left: 24px;
            }

            .text-section li {
                margin: 6px 0;
            }

            .text-section strong {
                color: #fff;
                font-weight: 600;
            }

            .text-section em {
                font-style: italic;
                color: #c0c0c0;
            }

            .tool-section {
                background: #2a3a2a;
                border-left: 4px solid #48bb78;
                padding: 16px;
                margin: 12px 0;
                border-radius: 6px;
            }

            .tool-header {
                color: #68d391;
                font-weight: 600;
                margin-bottom: 12px;
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .tool-icon {
                font-size: 18px;
            }

            .tool-name {
                font-size: 16px;
                font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
            }

            .tool-id {
                font-size: 11px;
                color: #666;
                margin-left: 12px;
            }

            .tool-params {
                background: #1e1e1e;
                padding: 12px;
                border-radius: 4px;
                margin: 8px 0;
                font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
                font-size: 13px;
                overflow-x: auto;
            }

            .tool-result {
                margin-top: 12px;
            }

            .tool-result-header {
                color: #68d391;
                font-weight: 600;
                margin-bottom: 8px;
                font-size: 14px;
            }

            .tool-result-content {
                background: #1e1e1e;
                padding: 12px;
                border-radius: 4px;
                font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
                font-size: 13px;
                color: #c0c0c0;
                white-space: pre-wrap;
                max-height: 400px;
                overflow-y: auto;
                line-height: 1.5;
            }

            .truncated-notice {
                color: #888;
                font-style: italic;
                margin-top: 8px;
                font-size: 12px;
            }

            .user-message .message-header {
                border-bottom-color: #4a90e2;
            }

            .assistant-message .message-header {
                border-bottom-color: #764ba2;
            }

            .footer {
                background: #3a3a3a;
                padding: 20px;
                text-align: center;
                color: #888;
                font-size: 14px;
                border-top: 1px solid #4a4a4a;
            }

            /* 滚动条样式 */
            ::-webkit-scrollbar {
                width: 8px;
                height: 8px;
            }

            ::-webkit-scrollbar-track {
                background: #2a2a2a;
            }

            ::-webkit-scrollbar-thumb {
                background: #555;
                border-radius: 4px;
            }

            ::-webkit-scrollbar-thumb:hover {
                background: #666;
            }

            /* 响应式设计 */
            @media (max-width: 768px) {
                body {
                    padding: 10px;
                }

                .container {
                    border-radius: 0;
                }

                .header {
                    padding: 20px;
                }

                .header h1 {
                    font-size: 22px;
                }

                .message-content {
                    padding-left: 0;
                }
            }
        </style>
        """

    def format_tool_use_html(self, tool: Dict[str, Any]) -> str:
        """格式化tool_use内容为HTML"""
        tool_name = html_module.escape(tool.get('name', 'Unknown'))
        tool_id = html_module.escape(tool.get('id', ''))
        tool_input = tool.get('input', {})

        html_parts = []
        html_parts.append('<div class="tool-section">')
        html_parts.append(f'  <div class="tool-header">')
        html_parts.append(f'    <span class="tool-icon">🔧</span>')
        html_parts.append(f'    <span class="tool-name">{tool_name}</span>')
        html_parts.append(f'    <span class="tool-id">ID: {tool_id}</span>')
        html_parts.append(f'  </div>')

        # 格式化输入参数
        if tool_input:
            params_json = html_module.escape(json.dumps(tool_input, indent=2, ensure_ascii=False))
            html_parts.append(f'  <div class="tool-params">{params_json}</div>')

        # 查找对应的tool_result
        tool_result = self.tool_results.get(tool.get('id'))
        if tool_result:
            html_parts.append(f'  <div class="tool-result">')
            html_parts.append(f'    <div class="tool-result-header">📤 工具结果</div>')

            content = tool_result['content']
            truncated = False

            # 如果内容太长，截断显示
            if len(content) > 1000:
                lines = content.split('\n')
                if len(lines) > 30:
                    content = '\n'.join(lines[:30])
                    truncated = len(lines) - 30
                else:
                    content = content[:1000]
                    truncated = True

            escaped_content = html_module.escape(content)
            html_parts.append(f'    <div class="tool-result-content">{escaped_content}</div>')

            if truncated:
                if isinstance(truncated, int):
                    html_parts.append(f'    <div class="truncated-notice">... (还有 {truncated} 行)</div>')
                else:
                    html_parts.append(f'    <div class="truncated-notice">... (内容已截断)</div>')

            html_parts.append(f'  </div>')

        html_parts.append('</div>')
        return '\n'.join(html_parts)

    def format_message_html(self, msg: Dict[str, Any]) -> str:
        """格式化单条消息为HTML"""
        role = msg.get('role', 'unknown')
        timestamp = msg.get('timestamp', '')
        content = msg.get('content', [])

        # 格式化时间戳
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            time_str = timestamp

        html_parts = []

        if role == 'user':
            icon = '👤'
            role_text = '用户'
            message_class = 'user-message'
        else:
            icon = '🤖'
            role_text = 'Claude'
            message_class = 'assistant-message'

        html_parts.append(f'<div class="message {message_class}">')
        html_parts.append(f'  <div class="message-header" onclick="this.parentElement.classList.toggle(\'collapsed\');">')
        html_parts.append(f'    <span class="message-icon">{icon}</span>')
        html_parts.append(f'    <div class="message-meta">')
        html_parts.append(f'      <span class="message-role">{role_text}</span>')
        html_parts.append(f'      <span class="message-timestamp">{time_str}</span>')

        # 显示token使用情况（仅助手消息）
        if role == 'assistant':
            usage = msg.get('usage', {})
            if usage:
                input_tokens = usage.get('input_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)
                cache_read = usage.get('cache_read_input_tokens', 0)
                html_parts.append(f'      <div class="message-tokens">')
                html_parts.append(f'        <span class="token-item">输入: {input_tokens}</span>')
                html_parts.append(f'        <span class="token-item">输出: {output_tokens}</span>')
                html_parts.append(f'        <span class="token-item">缓存: {cache_read}</span>')
                html_parts.append(f'      </div>')

        html_parts.append(f'    </div>')
        html_parts.append(f'  </div>')
        html_parts.append(f'  <div class="message-content">')

        # 处理消息内容
        for item in content:
            item_type = item.get('type')

            if item_type == 'thinking':
                thinking_text = html_module.escape(item.get('thinking', ''))
                html_parts.append(f'    <div class="thinking-section">')
                html_parts.append(f'      <div class="thinking-header" onclick="event.stopPropagation(); this.parentElement.classList.toggle(\'collapsed\'); this.nextElementSibling.classList.toggle(\'hidden\');">')
                html_parts.append(f'        <span class="collapse-icon">▼</span>')
                html_parts.append(f'        <span>💭 思考过程</span>')
                html_parts.append(f'      </div>')
                html_parts.append(f'      <div class="thinking-content">{thinking_text}</div>')
                html_parts.append(f'    </div>')

            elif item_type == 'text':
                text = item.get('text', '')
                # 处理特殊标记
                if '<ide_opened_file>' in text:
                    file_path = text.replace('<ide_opened_file>', '').replace('</ide_opened_file>', '').strip()
                    html_parts.append(f'    <div class="text-section">📂 <strong>打开文件:</strong> <code>{html_module.escape(file_path)}</code></div>')
                else:
                    # Markdown到HTML转换并高亮显示
                    markdown_html = self._markdown_to_html(text)
                    # 为Assistant的文本回复添加高亮
                    if role == 'assistant':
                        html_parts.append(f'    <div class="text-section highlight">{markdown_html}</div>')
                    else:
                        html_parts.append(f'    <div class="text-section">{markdown_html}</div>')

            elif item_type == 'tool_use':
                html_parts.append(f'    {self.format_tool_use_html(item)}')

        html_parts.append(f'  </div>')
        html_parts.append(f'</div>')

        return '\n'.join(html_parts)

    def _restore_html(self, grouped_messages: List[Dict[str, Any]]) -> str:
        """以HTML格式还原会话"""
        html_parts = []

        # HTML头部
        html_parts.append('<!DOCTYPE html>')
        html_parts.append('<html lang="zh-CN">')
        html_parts.append('<head>')
        html_parts.append('  <meta charset="UTF-8">')
        html_parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1.0">')
        html_parts.append('  <title>Claude Code 会话还原</title>')
        html_parts.append('  <!-- Highlight.js for syntax highlighting -->')
        html_parts.append('  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">')
        html_parts.append(self._get_html_css())
        html_parts.append('</head>')
        html_parts.append('<body>')
        html_parts.append('  <div class="container">')
        html_parts.append('    <div class="header">')
        html_parts.append('      <h1>Claude Code 会话还原</h1>')
        html_parts.append('      <div class="subtitle">完整的对话历史记录</div>')
        html_parts.append('    </div>')
        html_parts.append('    <div class="messages">')

        # 添加所有消息
        for msg in grouped_messages:
            html_parts.append(self.format_message_html(msg))

        html_parts.append('    </div>')
        html_parts.append('    <div class="footer">')
        html_parts.append('      <p>会话结束</p>')
        html_parts.append('    </div>')
        html_parts.append('  </div>')
        html_parts.append('  <!-- Highlight.js library -->')
        html_parts.append('  <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>')
        html_parts.append('  <script>')
        html_parts.append('    // Initialize syntax highlighting')
        html_parts.append('    hljs.highlightAll();')
        html_parts.append('  </script>')
        html_parts.append('</body>')
        html_parts.append('</html>')

        return '\n'.join(html_parts)


def scan_jsonl_files(directory: str) -> List[str]:
    """
    扫描目录中所有的jsonl文件，排除agent-前缀的文件
    返回符合条件的文件路径列表
    """
    directory_path = Path(directory)
    if not directory_path.exists():
        raise FileNotFoundError(f"目录不存在: {directory}")

    if not directory_path.is_dir():
        raise NotADirectoryError(f"不是有效的目录: {directory}")

    jsonl_files = []

    # 扫描所有.jsonl和.json文件
    for file_path in directory_path.glob('*.jsonl'):
        # 排除agent-前缀的文件
        if not file_path.name.startswith('agent-'):
            # 检查文件大小，跳过空文件
            if file_path.stat().st_size > 0:
                jsonl_files.append(str(file_path))

    # 也扫描.json文件（如示例中的bb81858c-f8ba-4a96-8750-79bac1934255.json）
    for file_path in directory_path.glob('*.json'):
        if not file_path.name.startswith('agent-'):
            if file_path.stat().st_size > 0:
                jsonl_files.append(str(file_path))

    return sorted(jsonl_files)


def process_single_file(input_file: str, output_dir: str, output_format: str) -> dict:
    """
    处理单个文件
    返回处理结果的统计信息
    """
    result = {
        'input_file': input_file,
        'success': False,
        'output_file': None,
        'error': None
    }

    try:
        restorer = ChatRestorer(input_file, output_format)
        output = restorer.restore()

        # 生成输出文件名
        input_path = Path(input_file)
        base_name = input_path.stem  # 不包含扩展名的文件名

        if output_format == 'markdown':
            output_file = Path(output_dir) / f"{base_name}_restored.md"
        elif output_format == 'html':
            output_file = Path(output_dir) / f"{base_name}_restored.html"
        else:
            output_file = Path(output_dir) / f"{base_name}_restored.txt"

        # 写入文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)

        result['success'] = True
        result['output_file'] = str(output_file)

    except Exception as e:
        result['error'] = str(e)

    return result


def batch_process_directory(directory: str, output_format: str = 'txt') -> None:
    """
    批量处理目录中的所有JSONL文件
    """
    print(f"📁 正在扫描目录: {directory}")

    # 扫描文件
    try:
        jsonl_files = scan_jsonl_files(directory)
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)

    if not jsonl_files:
        print("⚠️  未找到符合条件的JSONL文件（排除了agent-前缀和空文件）")
        return

    print(f"✅ 找到 {len(jsonl_files)} 个符合条件的文件")

    # 创建输出目录
    output_dir = Path(directory) / 'claude_parse'
    output_dir.mkdir(exist_ok=True)
    print(f"📂 输出目录: {output_dir}")
    print(f"📄 输出格式: {output_format.upper()}")
    print("")

    # 批量处理
    success_count = 0
    failed_count = 0

    for i, input_file in enumerate(jsonl_files, 1):
        file_name = Path(input_file).name
        print(f"[{i}/{len(jsonl_files)}] 处理中: {file_name} ... ", end='', flush=True)

        result = process_single_file(input_file, str(output_dir), output_format)

        if result['success']:
            print(f"✅ 成功")
            success_count += 1
        else:
            print(f"❌ 失败: {result['error']}")
            failed_count += 1

    # 输出统计信息
    print("")
    print("=" * 80)
    print(f"批量处理完成！")
    print(f"  成功: {success_count} 个文件")
    print(f"  失败: {failed_count} 个文件")
    print(f"  输出目录: {output_dir}")
    print("=" * 80)


def scan_jsonl_files(directory: str) -> List[str]:
    """
    扫描目录中所有的jsonl文件，排除agent-前缀的文件
    返回符合条件的文件路径列表
    """
    directory_path = Path(directory)
    if not directory_path.exists():
        raise FileNotFoundError(f"目录不存在: {directory}")

    if not directory_path.is_dir():
        raise NotADirectoryError(f"不是有效的目录: {directory}")

    jsonl_files = []

    # 扫描所有.jsonl和.json文件
    for file_path in directory_path.glob('*.jsonl'):
        # 排除agent-前缀的文件
        if not file_path.name.startswith('agent-'):
            # 检查文件大小，跳过空文件
            if file_path.stat().st_size > 0:
                jsonl_files.append(str(file_path))

    # 也扫描.json文件（如示例中的bb81858c-f8ba-4a96-8750-79bac1934255.json）
    for file_path in directory_path.glob('*.json'):
        if not file_path.name.startswith('agent-'):
            if file_path.stat().st_size > 0:
                jsonl_files.append(str(file_path))

    return sorted(jsonl_files)


def process_single_file(input_file: str, output_dir: str, output_format: str) -> dict:
    """
    处理单个文件
    返回处理结果的统计信息
    """
    result = {
        'input_file': input_file,
        'success': False,
        'output_file': None,
        'error': None
    }

    try:
        restorer = ChatRestorer(input_file, output_format)
        output = restorer.restore()

        # 生成输出文件名
        input_path = Path(input_file)
        base_name = input_path.stem  # 不包含扩展名的文件名

        if output_format == 'markdown':
            output_file = Path(output_dir) / f"{base_name}_restored.md"
        else:
            output_file = Path(output_dir) / f"{base_name}_restored.txt"

        # 写入文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)

        result['success'] = True
        result['output_file'] = str(output_file)

    except Exception as e:
        result['error'] = str(e)

    return result


def batch_process_directory(directory: str, output_format: str = 'txt') -> None:
    """
    批量处理目录中的所有JSONL文件
    """
    print(f"📁 正在扫描目录: {directory}")

    # 扫描文件
    try:
        jsonl_files = scan_jsonl_files(directory)
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)

    if not jsonl_files:
        print("⚠️  未找到符合条件的JSONL文件（排除了agent-前缀和空文件）")
        return

    print(f"✅ 找到 {len(jsonl_files)} 个符合条件的文件")

    # 创建输出目录
    output_dir = Path(directory) / 'claude_parse'
    output_dir.mkdir(exist_ok=True)
    print(f"📂 输出目录: {output_dir}")
    print(f"📄 输出格式: {output_format.upper()}")
    print("")

    # 批量处理
    success_count = 0
    failed_count = 0

    for i, input_file in enumerate(jsonl_files, 1):
        file_name = Path(input_file).name
        print(f"[{i}/{len(jsonl_files)}] 处理中: {file_name} ... ", end='', flush=True)

        result = process_single_file(input_file, str(output_dir), output_format)

        if result['success']:
            print(f"✅ 成功")
            success_count += 1
        else:
            print(f"❌ 失败: {result['error']}")
            failed_count += 1

    # 输出统计信息
    print("")
    print("=" * 80)
    print(f"批量处理完成！")
    print(f"  成功: {success_count} 个文件")
    print(f"  失败: {failed_count} 个文件")
    print(f"  输出目录: {output_dir}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Claude Code 会话还原工具 - 将JSONL格式的会话数据转换为可读格式',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 处理单个文件（使用默认文件case.jsonl）
  python3 restore_chat.py

  # 指定输入文件
  python3 restore_chat.py my_chat.jsonl

  # 输出为Markdown格式
  python3 restore_chat.py my_chat.jsonl --format markdown

  # 输出为HTML格式（可在浏览器中查看）
  python3 restore_chat.py my_chat.jsonl --format html

  # 批量处理目录中的所有JSONL文件
  python3 restore_chat.py --dir /path/to/chats

  # 批量处理目录并输出为HTML格式
  python3 restore_chat.py --dir /path/to/chats --format html
        """
    )

    parser.add_argument(
        'jsonl_file',
        nargs='?',
        default=None,
        help='输入的JSONL文件路径'
    )

    parser.add_argument(
        '-d', '--dir',
        dest='directory',
        help='批量处理指定目录中的所有JSONL文件（排除agent-前缀的文件）'
    )

    parser.add_argument(
        '-f', '--format',
        choices=['txt', 'markdown', 'md', 'html'],
        default='txt',
        help='输出格式: txt（文本）、markdown/md（Markdown）或 html（HTML网页）（默认: txt）'
    )

    args = parser.parse_args()

    # 统一处理格式参数
    if args.format in ['markdown', 'md']:
        output_format = 'markdown'
    elif args.format == 'html':
        output_format = 'html'
    else:
        output_format = 'txt'

    # 判断是批量处理还是单文件处理
    if args.directory:
        # 批量处理目录
        batch_process_directory(args.directory, output_format)
    else:
        # 单文件处理
        jsonl_file = args.jsonl_file or 'case.jsonl'

        try:
            restorer = ChatRestorer(jsonl_file, output_format)
            output = restorer.restore()

            # 根据格式选择输出文件扩展名
            input_path = Path(jsonl_file)
            base_name = input_path.stem

            if output_format == 'markdown':
                output_file = str(input_path.parent / f"{base_name}_restored.md")
            elif output_format == 'html':
                output_file = str(input_path.parent / f"{base_name}_restored.html")
            else:
                output_file = str(input_path.parent / f"{base_name}_restored.txt")

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output)

            print(f"✅ 会话已成功还原！")
            print(f"📄 输出格式: {output_format.upper()}")
            print(f"📄 输出文件: {output_file}")

            if output_format != 'html':
                print(f"\n预览前50行:")
                print("=" * 80)
                print('\n'.join(output.split('\n')[:50]))
            else:
                print(f"\n💡 提示: 请在浏览器中打开HTML文件以查看完整的交互式界面")

        except FileNotFoundError:
            print(f"❌ 错误: 找不到文件 '{jsonl_file}'", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"❌ 错误: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == '__main__':
    main()
