import os
import sys
import re
import json
import argparse
import datetime
from typing import List, Dict

# 尝试导入 OpenAI，如果不存在则提示用户安装
try:
    from openai import OpenAI
except ImportError:
    print("❌ Missing dependency: openai")
    print("👉 Please run: pip install openai")
    sys.exit(1)

def clean_ansi(text: str) -> str:
    """Removes ANSI escape sequences (colors, cursor moves) from raw terminal logs."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def parse_transcript(log_path: str) -> str:
    """Reads the raw 'script' log and makes it readable for the LLM."""
    if not os.path.exists(log_path):
        return ""
    
    with open(log_path, 'r', errors='ignore') as f:
        raw_data = f.read()
    
    clean_data = clean_ansi(raw_data)
    
    # 简单的启发式压缩：移除过长的自动生成输出，保留用户输入
    # 这里只是一个简单的处理，让 Token 不至于爆炸
    lines = clean_data.split('\n')
    compressed_lines = []
    for line in lines:
        if len(line) > 500:
            compressed_lines.append(line[:200] + "... [Output Truncated] ..." + line[-200:])
        else:
            compressed_lines.append(line)
            
    return "\n".join(compressed_lines)

def generate_summary(transcript: str, api_key: str, base_url: str = None) -> str:
    """Calls the LLM to analyze the session."""
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    system_prompt = """
    You are the "Context Cartographer". Your job is to analyze a terminal session transcript of a developer interacting with an AI coding assistant.
    
    Output a Markdown report with the following structure:
    
    # 🗺️ Session Evolution (Mermaid Graph)
    [Generate a mermaid TD graph showing the flow of tasks. Nodes are actions, edges are triggers/reasons.]
    
    # 📝 Key Decisions Log
    [A markdown table with columns: Time(Approx), Intent, Action, Outcome]
    
    # 🧠 Context Anchor
    [A concise summary paragraph (2-3 sentences) specifically designed to "load context" into the developer's brain next time they start. Mention unfinished tasks clearly.]
    
    # 🚧 Left Hanging
    [Bulleted list of immediate next steps or unresolved errors.]
    """
    
    user_prompt = f"Here is the session transcript. Analyze it:\n\n{transcript[-100000:]}" # 保留最后 100k 字符
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o", # 或者用户配置的其他模型
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Error generating summary: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description="Context Cartographer Analyzer")
    parser.add_argument("log_file", help="Path to the raw session log")
    parser.add_argument("--out", default=".context/session_summary.md", help="Output path for summary")
    args = parser.parse_args()

    # 1. Check API Key
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CARTOGRAPHER_KEY")
    if not api_key:
        # Fallback: Create a dummy report if no key (so functionality is visible)
        print("⚠️  No API Key found (OPENAI_API_KEY). Generating placeholder report.")
        dummy_report = """# 🗺️ Session Evolution
> **⚠️ API Key Missing**: Please export OPENAI_API_KEY to enable AI analysis.

# 📝 Raw Log Stats
- Log File: {}
- Size: {} bytes
""".format(args.log_file, os.path.getsize(args.log_file))
        
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, 'w') as f:
            f.write(dummy_report)
        return

    # 2. Parse & Analyze
    print("🧠 Analyzing session context...")
    transcript = parse_transcript(args.log_file)
    if not transcript.strip():
        print("⚠️  Empty transcript. Nothing to analyze.")
        return

    summary = generate_summary(transcript, api_key)
    
    # 3. Save
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w') as f:
        f.write(summary)
    
    print(f"✨ Context Map saved to: {args.out}")

if __name__ == "__main__":
    main()
