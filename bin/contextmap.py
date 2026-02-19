import os
import sys
import re
import json
import argparse
import datetime
from typing import List, Dict

# No external dependencies required for CLI-piping mode
# try:
#     from openai import OpenAI
# except ImportError:
#     pass # Handled gracefully if needed for fallback

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

def generate_summary(transcript: str, model: str = None) -> str:
    """Uses Claude Code (CLI) itself to summarize the log via subprocess."""
    
    system_prompt = """
    You are 'ContextMap'. Analyze the attached session transcript.
    Output a Markdown report with:
    1. # 🗺️ Session Evolution (Mermaid Graph)
    2. # 📝 Key Decisions Log (Table)
    3. # 🧠 Context Anchor (Summary for next session)
    4. # 🚧 Left Hanging (Next steps)
    
    Keep it concise. Use the transcript provided below.
    """
    
    # We construct a prompt file to feed into Claude
    prompt_content = f"{system_prompt}\n\nTRANSCRIPT:\n{transcript[-80000:]}" # Limit to 80k chars to be safe
    
    import tempfile
    import subprocess
    
    # Create temp file for prompt content
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt") as tmp:
        tmp.write(prompt_content)
        tmp_path = tmp.name
        
    try:
        # Construct the Claude CLI command
        # Strategy: cat prompt.txt | claude -p "Summarize this input"
        # Or: claude -p "$(cat prompt.txt)"
        
        real_claude = os.getenv("REAL_CLAUDE_PATH") or "claude" 
        
        # We assume 'claude' accepts prompt via argument. 
        # Since prompt is large, we might hit ARG_MAX.
        # Ideally, we should check if claude supports file input or stdin.
        # For now, let's try the pipe approach which is standard for CLI tools.
        
        # We run: cat tmp_path | claude -p "Analyze this input"
        # Note: We must ensure we don't trigger the wrapper script again (infinite loop).
        # The Wrapper script sets REAL_CLAUDE_PATH, so we are safe if running from there.
        
        # Command: claude --print "Analyze this file" (if supported)
        # Or simply rely on stdin if supported.
        
        # Let's try to run it directly with the prompt as text, catching the output.
        # This assumes the user is authenticated in the CLI environment.
        
        # Use subprocess to pipe
        with open(tmp_path, 'r') as f:
            process = subprocess.run(
                [real_claude, "-p", "Analyze the provided transcript context."], 
                stdin=f,
                text=True, 
                capture_output=True
            )
        
        if process.returncode != 0:
            return f"❌ Claude CLI Error: {process.stderr}"
            
        return process.stdout

    except Exception as e:
        return f"❌ Execution Error: {str(e)}"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def main():
    parser = argparse.ArgumentParser(description="ContextMap Analyzer")
    parser.add_argument("log_file", help="Path to the raw session log")
    parser.add_argument("--out", default=".context/session_summary.md", help="Output path for summary")
    parser.add_argument("--model", default=None, help="The model used in the session")
    args = parser.parse_args()

    # 2. Parse & Analyze
    print("🧠 Analyzing session context...")
    transcript = parse_transcript(args.log_file)
    if not transcript.strip():
        print("⚠️  Empty transcript. Nothing to analyze.")
        return

    # Call summary generation (which now uses Claude CLI subprocess)
    summary = generate_summary(transcript, model=args.model)
    
    # 3. Save
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w') as f:
        f.write(summary)
    
    print(f"✨ Context Map saved to: {args.out}")

if __name__ == "__main__":
    main()

