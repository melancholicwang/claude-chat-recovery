#!/usr/bin/env python3
"""
Claude Code 会话还原程序
从 case.jsonl 还原完整的对话，包括 thinking、tool 调用和结果
"""

import json
import sys
from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime


class ChatRestorer:
    def __init__(self, jsonl_file: str):
        self.jsonl_file = jsonl_file
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

    def restore(self) -> str:
        """还原完整会话"""
        self.load_data()
        grouped_messages = self.group_messages()

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


def main():
    if len(sys.argv) > 1:
        jsonl_file = sys.argv[1]
    else:
        jsonl_file = 'case.jsonl'

    try:
        restorer = ChatRestorer(jsonl_file)
        output = restorer.restore()

        # 输出到文件
        output_file = jsonl_file.replace('.jsonl', '_restored.txt')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)

        print(f"✅ 会话已成功还原！")
        print(f"📄 输出文件: {output_file}")
        print(f"\n预览前50行:")
        print("=" * 80)
        print('\n'.join(output.split('\n')[:50]))

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
