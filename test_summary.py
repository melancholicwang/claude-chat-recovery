#!/usr/bin/env python3
"""生成会话统计摘要"""

import json
import sys

def analyze_jsonl(file_path):
    stats = {
        'total_lines': 0,
        'queue_operations': 0,
        'user_messages': 0,
        'assistant_messages': 0,
        'tool_uses': 0,
        'tool_results': 0,
        'thinking_blocks': 0,
        'text_responses': 0,
        'unique_message_ids': set(),
        'total_input_tokens': 0,
        'total_output_tokens': 0,
        'total_cache_read_tokens': 0,
    }
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            stats['total_lines'] += 1
            try:
                obj = json.loads(line.strip())
                obj_type = obj.get('type')
                
                if obj_type == 'queue-operation':
                    stats['queue_operations'] += 1
                elif obj_type == 'user':
                    stats['user_messages'] += 1
                    content = obj.get('message', {}).get('content', [])
                    for item in content:
                        if item.get('type') == 'tool_result':
                            stats['tool_results'] += 1
                elif obj_type == 'assistant':
                    stats['assistant_messages'] += 1
                    message = obj.get('message', {})
                    msg_id = message.get('id')
                    if msg_id:
                        stats['unique_message_ids'].add(msg_id)
                    
                    # 统计usage
                    usage = message.get('usage', {})
                    if usage:
                        stats['total_input_tokens'] += usage.get('input_tokens', 0)
                        stats['total_output_tokens'] += usage.get('output_tokens', 0)
                        stats['total_cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)
                    
                    # 统计content类型
                    content = message.get('content', [])
                    for item in content:
                        item_type = item.get('type')
                        if item_type == 'thinking':
                            stats['thinking_blocks'] += 1
                        elif item_type == 'text':
                            stats['text_responses'] += 1
                        elif item_type == 'tool_use':
                            stats['tool_uses'] += 1
                            
            except json.JSONDecodeError:
                continue
    
    stats['unique_message_ids'] = len(stats['unique_message_ids'])
    return stats

if __name__ == '__main__':
    file_path = sys.argv[1] if len(sys.argv) > 1 else 'case.jsonl'
    stats = analyze_jsonl(file_path)
    
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 18 + "会话统计摘要" + " " * 24 + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    print(f"📄 文件: {file_path}")
    print(f"📊 总行数: {stats['total_lines']}")
    print()
    print("消息统计:")
    print(f"  • 队列操作: {stats['queue_operations']}")
    print(f"  • 用户消息行: {stats['user_messages']}")
    print(f"  • 助手消息行: {stats['assistant_messages']}")
    print(f"  • 唯一助手消息数: {stats['unique_message_ids']}")
    print()
    print("内容统计:")
    print(f"  • 💭 思考块: {stats['thinking_blocks']}")
    print(f"  • 💬 文本回复: {stats['text_responses']}")
    print(f"  • 🔧 工具调用: {stats['tool_uses']}")
    print(f"  • 📤 工具结果: {stats['tool_results']}")
    print()
    print("Token 统计:")
    print(f"  • 输入: {stats['total_input_tokens']:,}")
    print(f"  • 输出: {stats['total_output_tokens']:,}")
    print(f"  • 缓存读取: {stats['total_cache_read_tokens']:,}")
    print(f"  • 总计: {stats['total_input_tokens'] + stats['total_output_tokens']:,}")
