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
    # 1. Remove CSI sequences (Cursor movements, colors, etc.)
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)
    
    # 2. Remove other control characters but keep newlines
    # This removes Backspaces (\x08) which can mess up logging
    text = re.sub(r'[\x00-\x09\x0B\x0C\x0E-\x1F\x7F]', '', text)
    return text

def smart_compress_transcript(raw_text: str) -> str:
    """
    Intelligently compresses the session log to keep the 'Narrative' 
    but discard the 'Bulk Data' (like large file reads, long outputs).
    """
    # 1. Clean basic ANSI
    cleaned = clean_ansi(raw_text)
    
    lines = cleaned.split('\n')
    compressed = []
    
    for line in lines:
        line_strip = line.strip()
        
        # 1. Detect User Prompt (Common CLI prompts)
        if line_strip.startswith("> ") or line_strip.startswith("❯ "):
            # Add extra newline for separation
            compressed.append(f"\n--- USER STEP ---\n{line_strip}")
            continue
            
        # 2. Skip useless progress lines (heuristic)
        if "Resolving..." in line or "Fetching..." in line or "Downloading..." in line:
            continue
            
        # 3. Truncate extremely long lines (like base64 or minified code)
        if len(line) > 300:
            line = line[:100] + f" ... [{len(line)-200} chars truncated] ... " + line[-100:]
            
        compressed.append(line)
        
    # Re-join
    full_text = "\n".join(compressed)
    
    # 4. Aggressive block deduplication (if tool output repeats)
    # Use regex to replace massive blocks of similar looking lines (like file reads)
    # This is safer than line-by-line state machines which can break easily
    
    return full_text

def parse_transcript(log_path: str) -> str:
    """Reads and compresses the log."""
    if not os.path.exists(log_path):
        return ""
    
    try:
        with open(log_path, 'r', errors='replace') as f:
            raw_data = f.read()
            
        return smart_compress_transcript(raw_data)
    except Exception as e:
        return f"[Error reading log: {str(e)}]"

def generate_summary(transcript: str, old_summary: str = "", model: str = None) -> str:
    """Uses Claude Code (CLI) itself to summarize the log via subprocess."""
    
    system_prompt = """
    You are 'ContextMap'. Analyze the provided 'Previous Session Context' and 'Current Session Transcript'.
    
    Your goal is to UPDATE the project map. Do not just summarize the new log; integrate it into the existing history.
    
    Output a Markdown report with:
    1. # 🗺️ Session Evolution (Mermaid Graph) -> Grow this graph. Add new nodes for today's work.
    2. # 📝 Key Decisions Log (Table) -> Append new decisions.
    3. # 🧠 Context Anchor -> Update this to reflect the CURRENT status after recent changes.
    4. # 🚧 Left Hanging -> Remove solved items, add new blockers.
    
    Keep it concise.
    """
    
    # We construct a prompt file to feed into Claude
    prompt_content = f"{system_prompt}\n\n=== PREVIOUS SESSION CONTEXT ===\n{old_summary}\n\n=== CURRENT SESSION TRANSCRIPT ===\n{transcript[-80000:]}" 
    
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

def cleanup_old_logs(log_dir: str, days: int = 2):
    """Deletes log files older than X days."""
    try:
        # Resolve absolute path just to be sure
        abs_log_dir = os.path.abspath(log_dir)
        
        if not os.path.exists(abs_log_dir):
            return
            
        cutoff = datetime.datetime.now().timestamp() - (days * 86400)
        
        count = 0
        for f in os.listdir(abs_log_dir):
            if not f.endswith(".log"): continue
            
            path = os.path.join(abs_log_dir, f)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    count += 1
            except OSError:
                pass
                    
        if count > 0:
            print(f"🧹 Cleaned up {count} old log files.")
            
    except Exception as e:
        # Housekeeping should never crash the app
        print(f"⚠️  Cleanup warning: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="ContextMap Analyzer")
    parser.add_argument("log_file", help="Path to the raw session log")
    parser.add_argument("--out", default=".context/session_summary.md", help="Output path for summary")
    parser.add_argument("--model", default=None, help="The model used in the session")
    args = parser.parse_args()

    # 0. Cleanup Old Logs (Housekeeping)
    # Ensure we look in the directory of the log file provided
    try:
        log_dir = os.path.dirname(args.log_file)
        if log_dir: # Only if a directory component exists
            cleanup_old_logs(log_dir)
    except Exception:
        pass # Ignore errors in housekeeping

    # 2. Parse & Analyze
    print("🧠 Analyzing session context...")
    transcript = parse_transcript(args.log_file)
    if not transcript.strip():
        print("⚠️  Empty transcript. Nothing to analyze.")
        return

    # Load Previous Summary (Recursive Memory)
    old_summary = ""
    if os.path.exists(args.out):
        try:
            with open(args.out, 'r') as f:
                old_summary = f.read()
        except:
            pass

    # Call summary generation (which now uses Claude CLI subprocess)
    summary = generate_summary(transcript, old_summary=old_summary, model=args.model)
    
    # 3. Save
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w') as f:
        f.write(summary)
    
    print(f"✨ Context Map saved to: {args.out}")

if __name__ == "__main__":
    main()

