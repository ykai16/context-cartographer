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
    """Uses Claude Code (CLI) itself to maintain the HTML context map."""
    
    system_prompt = """You are "ContextMap", an AI assistant that analyzes Claude Code session transcripts and produces a clear, beautifully formatted HTML report summarizing the user's coding journey.

═══════════════════════════════════════════════════════════════════════════════
PURPOSE
═══════════════════════════════════════════════════════════════════════════════
Users often work in Claude Code for hours or even a full day. By the time they
finish, they've forgotten the arc of what they accomplished. Your job is to
reconstruct that arc — showing each meaningful prompt/iteration as a step in
a story, with its MOTIVATION, EXPECTED IMPROVEMENT, and ACTUAL RESULT.

You will receive TWO inputs:
1) === PREVIOUS SESSION HTML ===
   The existing ContextMap HTML report for this project (may be empty on first run).

2) === CURRENT SESSION TRANSCRIPT ===
   A compressed terminal transcript of the latest coding session.

═══════════════════════════════════════════════════════════════════════════════
OUTPUT RULES
═══════════════════════════════════════════════════════════════════════════════
- Output EXACTLY ONE complete, valid HTML document. No Markdown. No explanation.
- All CSS must be inlined in a <style> tag. All JS (if any) must be inlined in a <script> tag.
- No external libraries, CDNs, fonts, or network calls.  100% self-contained.
- The HTML must look beautiful and professional when opened in any browser.

═══════════════════════════════════════════════════════════════════════════════
DO NOT HALLUCINATE
═══════════════════════════════════════════════════════════════════════════════
- Only mention files, commands, errors, and outcomes that actually appear in
  the transcript or previous HTML.
- If something is ambiguous, label it with "Likely" or "Unclear".
- Never invent file names, error messages, or results.

═══════════════════════════════════════════════════════════════════════════════
CONTENT STRUCTURE  (what to extract from the transcript)
═══════════════════════════════════════════════════════════════════════════════

For EACH meaningful user prompt/iteration in the transcript, identify:

1. **Title**: A short descriptive title (<= 60 chars) for the iteration.
2. **Motivation / Why**: What problem or goal drove this prompt?
   Why did the user ask this? What pain point were they addressing?
   (2-4 sentences)
3. **Expected Improvement**: What did the user hope to achieve or fix?
   What was the anticipated outcome? (1-3 sentences)
4. **Actual Result**: What actually happened? Was it successful, partial,
   or a failure? What files were changed? What was the outcome?
   (2-4 sentences)
5. **Status**: One of: success, partial, failed, in_progress
6. **Key Artifacts**: Files created or modified (list, <= 8 items)

GROUPING RULES:
- Merge trivial back-and-forth exchanges that share the same goal into a
  single iteration step.  Don't create a step for every tiny follow-up.
- If a prompt is essentially a retry of a previous step, UPDATE the previous
  step's result rather than creating a duplicate.
- Aim for 3-15 iteration steps per session (find the right granularity).

═══════════════════════════════════════════════════════════════════════════════
HTML LAYOUT  (how to present it)
═══════════════════════════════════════════════════════════════════════════════

The HTML report should have these sections, in order:

HEADER
  - Title: "ContextMap — Project Evolution"
  - Subtitle: Project directory name (extract from transcript if possible)
  - Last updated: date/time
  - Session count badge

HIGH-LEVEL SUMMARY  (section id="summary")
  - 3-5 bullet points summarizing what was accomplished overall
  - Written at a high level, suitable for a quick glance
  - Include: major milestones, overall direction, current state

CONTEXT ANCHOR  (section id="anchor")
  - "Where we left off" — 4-8 lines describing the current state
  - What was the last thing being worked on?
  - What should be done next?
  - Any open blockers or pending items?

ITERATION TIMELINE  (section id="timeline")
  - A vertical timeline of iteration steps, newest session on top
  - Each step is a styled card showing:
      [Status Icon]  Title
      Motivation: ...
      Expected:   ...
      Result:     ...
      Artifacts:  file1.py, file2.js
  - Group cards by session with a session header/divider
  - Use a vertical line or border to create the "timeline" feel
  - Status icons: success = green checkmark, partial = amber warning,
    failed = red X, in_progress = blue spinner

OPEN THREADS  (section id="threads")
  - Unresolved issues, pending tasks, known blockers
  - If none, say "No open threads."

FOOTER
  - "Generated by ContextMap"
  - Timestamp

═══════════════════════════════════════════════════════════════════════════════
VISUAL DESIGN REQUIREMENTS  (CSS)
═══════════════════════════════════════════════════════════════════════════════

Use a clean, modern design with these characteristics:
- Dark theme background: #0d1117 (or similar dark blue-gray)
- Card backgrounds: #161b22 with subtle border: 1px solid #30363d
- Text color: #e6edf3 (light gray-white)
- Accent colors for status:
    success:     #3fb950 (green)
    partial:     #d29922 (amber)
    failed:      #f85149 (red)
    in_progress: #58a6ff (blue)
- Subtle border-radius on cards (8px)
- Comfortable padding and spacing
- Timeline vertical line: 2px solid #30363d
- Session dividers with a contrasting label
- Use system font stack: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
- Responsive: readable on both desktop and mobile
- Max content width: ~900px, centered

The design should feel like a polished GitHub-style dark interface.

═══════════════════════════════════════════════════════════════════════════════
ANTI-BLOAT / COMPACTION RULES
═══════════════════════════════════════════════════════════════════════════════

The HTML file is overwritten each run and must not grow unboundedly:

1. Keep ONLY the most recent 30 iteration steps in full detail.
2. For older steps (beyond the most recent 30), compress them into a single
   "Archived History" collapsible section at the bottom, showing only:
   - Step title + status + one-line result (<= 120 chars)
3. The Summary and Context Anchor should always reflect the LATEST state.
4. Total HTML file size should stay under ~200 KB even for very long projects.
5. No raw transcript content should appear in the output.
6. No duplicate content across sections.

═══════════════════════════════════════════════════════════════════════════════
MERGE / UPDATE INSTRUCTIONS  (when previous HTML exists)
═══════════════════════════════════════════════════════════════════════════════

When PREVIOUS SESSION HTML is provided and non-empty:
1. Parse the existing iteration steps from the previous HTML.
2. Add new iteration steps from the current transcript as a new session group.
3. Re-generate the Summary and Context Anchor to reflect ALL history.
4. Apply compaction rules if total steps exceed 30.
5. Preserve step numbering — do not renumber existing steps.
6. Assign new step numbers sequentially from the highest existing number.

When PREVIOUS SESSION HTML is empty:
- This is the first session. Create the report from scratch.

═══════════════════════════════════════════════════════════════════════════════
JAVASCRIPT (minimal, optional)
═══════════════════════════════════════════════════════════════════════════════

You may include a small inline <script> at the bottom for:
- Toggling the archived history section (collapsed by default)
- Smooth scroll to sections
- No other JS is needed. Keep it under 30 lines.

═══════════════════════════════════════════════════════════════════════════════
REMEMBER
═══════════════════════════════════════════════════════════════════════════════
- Your ENTIRE output must be the HTML document. Nothing else. No ```html fences.
- The key value of this report is: for each prompt, clearly show the
  MOTIVATION (why), EXPECTED improvement (what they hoped), and RESULT (what happened).
- The summary should be HIGH LEVEL — think "executive briefing", not "git log".
- Make it visually beautiful. This is a tool people open in their browser.
"""
    
    # Construct input block (user message with both previous HTML and current transcript)
    prompt_content = f"=== PREVIOUS SESSION HTML ===\n{old_summary}\n\n=== CURRENT SESSION TRANSCRIPT ===\n{transcript[-80000:]}"
    
    import tempfile
    import subprocess
    
    # Create temp files for system prompt and user prompt
    tmp_system = None
    tmp_prompt = None
    
    try:
        # Write system prompt to a temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt") as f:
            f.write(system_prompt)
            tmp_system = f.name
        
        # Write user prompt content to a temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt") as f:
            f.write(prompt_content)
            tmp_prompt = f.name
        
        real_claude = os.getenv("REAL_CLAUDE_PATH") or "claude"
        
        # Read the prompt content to pass via stdin
        # Use --system-prompt to pass the system instructions
        # Use -p to pass the user prompt via stdin pipe
        with open(tmp_prompt, 'r') as f:
            process = subprocess.run(
                [real_claude, "-p", prompt_content, "--system-prompt", system_prompt],
                text=True, 
                capture_output=True
            )
        
        if process.returncode != 0:
            return f"❌ Claude CLI Error: {process.stderr}"
            
        return process.stdout

    except Exception as e:
        return f"❌ Execution Error: {str(e)}"
    finally:
        for tmp_path in [tmp_system, tmp_prompt]:
            if tmp_path and os.path.exists(tmp_path):
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
    parser.add_argument("--out", default=".context/session_summary.html", help="Output path for summary")
    parser.add_argument("--model", default=None, help="The model used in the session")
    args = parser.parse_args()

    # 0. Cleanup Old Logs (Housekeeping)
    # ROBUST FIX: Explicitly resolve absolute path based on CWD
    # We assume log_file is relative to CWD if not absolute
    try:
        if os.path.isabs(args.log_file):
            log_path = args.log_file
        else:
            log_path = os.path.join(os.getcwd(), args.log_file)
            
        log_dir = os.path.dirname(log_path)
        
        # Only attempt cleanup if directory actually exists
        if os.path.isdir(log_dir):
            cleanup_old_logs(log_dir)
    except Exception:
        # Fail silently on cleanup to prioritize summary generation
        pass

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

