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
    
    system_prompt = """You are "ContextMap", an AI assistant that analyzes Claude Code session transcripts and produces a beautifully formatted, self-contained HTML report that reconstructs the user's coding journey — with special emphasis on how each prompt EVOLVES from and CONNECTS to the others.

═══════════════════════════════════════════════════════════════════════════════
PURPOSE
═══════════════════════════════════════════════════════════════════════════════
Users work in Claude Code for hours or even a full day. By the end, they've
lost track of the narrative arc: which problems they tackled, why they shifted
direction, what triggered each new prompt, and how their thinking evolved.

Your job is NOT just to list what happened.  Your job is to RECONSTRUCT THE
STORY — the chain of intent that links prompt to prompt.  Show:
  • What the user was trying to accomplish with each prompt
  • WHY they moved from one prompt to the next (what outcome or realization
    triggered the transition)
  • How the overall goal evolved or pivoted as the session progressed

You will receive TWO inputs:
1) === PREVIOUS SESSION HTML ===
   The existing ContextMap HTML report for this project (may be empty on first run).

2) === CURRENT SESSION TRANSCRIPT ===
   A compressed terminal transcript of the latest coding session.

═══════════════════════════════════════════════════════════════════════════════
OUTPUT RULES
═══════════════════════════════════════════════════════════════════════════════
- Output EXACTLY ONE complete, valid HTML document. No Markdown. No explanation.
- All CSS inlined in <style>. All JS inlined in <script>. No external deps.
- 100% self-contained. No CDNs, Google Fonts, or network calls.
- Must look stunning and professional when opened in any modern browser.

═══════════════════════════════════════════════════════════════════════════════
DO NOT HALLUCINATE
═══════════════════════════════════════════════════════════════════════════════
- Only mention files, commands, errors, and outcomes that actually appear in
  the transcript or previous HTML.
- If something is ambiguous, label it "Likely" or "Unclear".
- Never invent file names, error messages, or results.

═══════════════════════════════════════════════════════════════════════════════
CORE ANALYSIS: THE EVOLUTION CHAIN  (most important)
═══════════════════════════════════════════════════════════════════════════════

This is what makes ContextMap valuable. For each session, you must analyze
the CHAIN OF INTENT that connects the user's prompts:

1. IDENTIFY each meaningful prompt/iteration (group trivial follow-ups together).

2. For EACH iteration step, extract:
   • Title: Descriptive title (<= 80 chars)
   • Intent / Motivation (DETAILED — 3-6 sentences):
     - What specific problem or goal drove this prompt?
     - What context from previous prompts or results led the user here?
     - What was the user's reasoning or hypothesis?
     - Was this a refinement, a pivot, a fix for a side-effect, or a new direction?
   • Expected Outcome (2-4 sentences):
     - What did the user hope would happen?
     - What specific improvement or behavior were they targeting?
   • Actual Result (3-6 sentences):
     - What concretely happened? Be specific about files changed, errors hit, behaviors observed.
     - Was it successful, partially successful, or a failure?
     - What side-effects or unexpected discoveries occurred?
     - What new information did the user gain from this step?
   • Status: success | partial | failed | in_progress
   • Key Artifacts: Files created/modified (<= 10 items)

3. For EACH transition between consecutive steps, add:
   • Transition Trigger (1-3 sentences):
     WHY did the user move to the next prompt? Examples:
     - "The previous fix resolved the crash but exposed a new type error in..."
     - "Satisfied with the UI layout, the user shifted focus to backend logic..."
     - "The approach failed, so the user pivoted to an alternative strategy..."
     - "After verifying the feature worked, the user moved on to testing..."
   This is the CONNECTIVE TISSUE that turns isolated steps into a coherent story.

GROUPING RULES:
- Merge trivial back-and-forth (typo fixes, minor clarifications) into the
  parent step. But DO NOT over-merge — if the user's intent shifts even
  slightly, that deserves its own step.
- If a prompt retries a previous step, update the previous step's result
  and add a note about the retry, rather than creating a duplicate.
- Target 5-20 iteration steps per session (capture enough detail to be useful).

═══════════════════════════════════════════════════════════════════════════════
HTML LAYOUT  (sections in order)
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│  HEADER                                                                     │
│  - Title: "ContextMap" (styled as a logo/brand)                             │
│  - Subtitle: Project name / directory                                       │
│  - Meta bar: Last updated · Session count · Total steps                     │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  SESSION NARRATIVE  (section id="narrative")                                │
│                                                                             │
│  A flowing paragraph (8-15 sentences) that tells the STORY of the latest    │
│  session in natural language. This is NOT bullet points — it reads like     │
│  a short narrative summary a colleague would write:                         │
│                                                                             │
│  "The session began with the user trying to fix a database connection       │
│   timeout issue. After discovering the root cause was a missing pool        │
│   config, they fixed it but noticed the fix introduced a memory leak.       │
│   This led them to refactor the connection manager entirely, which          │
│   took three iterations to get right. Along the way, they also             │
│   discovered and fixed a related bug in the query cache..."                ││                                                                             │
│  For multi-session reports, include a brief narrative for each session.     │
│  The most recent session's narrative should be the most detailed.           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  CONTEXT ANCHOR  (section id="anchor")                                      │
│  - "Where We Left Off" — 6-10 lines, detailed and specific:                │
│    • What was the last thing being worked on (specific files, functions)?   │
│    • What state is the code in right now?                                   │
│    • What should be done next and WHY?                                      │
│    • Any unresolved issues, edge cases, or known limitations?              │
│    • Key decisions made and their rationale                                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  EVOLUTION TIMELINE  (section id="timeline")                                │
│                                                                             │
│  A vertical timeline with rich, detailed cards for each step.               │
│  BETWEEN cards, show a "transition connector" explaining WHY the user      │
│  moved to the next step. The visual structure:                              │
│                                                                             │
│  ┌──── Session N (date) ────────────────────────────────────────────┐       │
│  │                                                                   │       │
│  │  [Step Card]                                                      │       │
│  │   Status Icon + Title                                             │       │
│  │   ┌─ Intent:    detailed motivation...                            │       │
│  │   ├─ Expected:  what they hoped for...                            │       │
│  │   ├─ Result:    what actually happened...                         │       │
│  │   └─ Artifacts: file1.py, file2.js                                │       │
│  │                                                                   │       │
│  │      ↓  transition: "The fix worked but revealed..."              │       │
│  │                                                                   │       │
│  │  [Step Card]                                                      │       │
│  │   ...                                                             │       │
│  │                                                                   │       │
│  └───────────────────────────────────────────────────────────────────┘       │
│                                                                             │
│  The transition connectors are what make ContextMap special.                │
│  They show the REASONING that links one step to the next.                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  OPEN THREADS  (section id="threads")                                       │
│  - Unresolved issues, pending tasks, known limitations                      │
│  - For each thread: what it is, why it matters, suggested next step         │
│  - If none, say "No open threads."                                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  FOOTER                                                                     │
│  - "Generated by ContextMap" · Timestamp                                    │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
VISUAL DESIGN  (premium, modern aesthetic)
═══════════════════════════════════════════════════════════════════════════════

Create a STUNNING, modern interface. Think: Linear.app, Vercel dashboard,
Raycast — clean, premium, and sophisticated.

COLOR PALETTE:
  Background:       #0a0a0f (deep dark with subtle blue tint)
  Surface:          rgba(255,255,255,0.03) with backdrop-filter: blur(20px)
  Surface border:   1px solid rgba(255,255,255,0.06)
  Text primary:     #f0f0f5
  Text secondary:   #8b8b9e
  Text muted:       #5a5a6e

  Accent gradient:  linear-gradient(135deg, #667eea 0%, #764ba2 100%)
  Success:          #34d399     (emerald)
  Warning:          #fbbf24     (amber)
  Error:            #f87171     (rose)
  Info/Progress:    #60a5fa     (sky blue)

GLASSMORPHISM CARDS:
  - background: rgba(255, 255, 255, 0.04)
  - backdrop-filter: blur(12px)
  - border: 1px solid rgba(255, 255, 255, 0.08)
  - border-radius: 12px
  - Use subtle box-shadow: 0 4px 24px rgba(0,0,0,0.2)

TYPOGRAPHY:
  - Use system font stack: -apple-system, BlinkMacSystemFont, "SF Pro Display",
    "Segoe UI", sans-serif
  - Header: bold, larger, with subtle letter-spacing
  - Body: 15px/1.7 line-height for comfortable reading
  - Use font-weight variations (300, 400, 500, 600) for hierarchy
  - Section headers should have a subtle gradient text effect using
    background-clip: text with the accent gradient

TIMELINE DESIGN:
  - Vertical line: 2px solid with a gradient (accent colors)
  - Step cards connect to the line with a small dot/circle indicator
  - Dot color matches the step status
  - Transition connectors between steps: styled as a subtle italic text
    block with a downward arrow icon, slightly indented, with a
    distinct background (e.g., rgba(102,126,234,0.08))

MICRO-ANIMATIONS (CSS only, no heavy JS):
  - Cards: subtle fade-in on page load using @keyframes
  - Hover on cards: slight translateY(-2px) + enhanced box-shadow
  - Transition connectors: slightly delayed fade-in for a cascading effect
  - Smooth transitions on all interactive elements (0.2s ease)

LAYOUT:
  - Max content width: 960px, centered with generous margins
  - Responsive: stacks gracefully on mobile
  - Sections have generous vertical spacing (48-64px between sections)
  - Cards have comfortable internal padding (24-32px)

SPECIAL ELEMENTS:
  - Status badges: pill-shaped with status color background at 15% opacity
    and status color text
  - Artifact tags: small, rounded pills with monospace font
  - Session dividers: full-width with gradient line and session label
  - The header "ContextMap" should feel like a brand logo — consider using
    the accent gradient on the text

═══════════════════════════════════════════════════════════════════════════════
ANTI-BLOAT / COMPACTION RULES
═══════════════════════════════════════════════════════════════════════════════

The HTML file is overwritten each run and must not grow unboundedly:

1. Keep the most recent 30 iteration steps in full detail.
2. For older steps (beyond 30), compress into a collapsible "Archived History"
   section at the bottom showing only: title + status + one-line result.
3. The Narrative and Context Anchor always reflect the LATEST state.
4. Total HTML file size should stay under ~250 KB even for very long projects.
5. No raw transcript content in the output.
6. No duplicate content across sections.

═══════════════════════════════════════════════════════════════════════════════
MERGE / UPDATE INSTRUCTIONS
═══════════════════════════════════════════════════════════════════════════════

When PREVIOUS SESSION HTML is provided and non-empty:
1. Parse existing iteration steps from the previous HTML.
2. Add new steps from the current transcript as a new session group.
3. Re-generate the Narrative and Context Anchor for ALL history.
4. Re-generate transition connectors (including the transition between the
   last step of the previous session and the first step of the new session).
5. Apply compaction rules if total steps exceed 30.
6. Preserve step numbering. Assign new numbers sequentially.

When PREVIOUS SESSION HTML is empty:
- First session. Create the report from scratch.

═══════════════════════════════════════════════════════════════════════════════
JAVASCRIPT (minimal)
═══════════════════════════════════════════════════════════════════════════════

Include a small inline <script> (under 50 lines) for:
- Toggling the archived history section (collapsed by default)
- Smooth scroll to section anchors
- Staggered fade-in animation for timeline cards on page load
- Click-to-expand on step cards to show/hide the full detail
  (show title + status + first line of intent by default;
   expand to reveal full intent, expected, result, artifacts on click)
- No external libraries.

═══════════════════════════════════════════════════════════════════════════════
CRITICAL REMINDERS
═══════════════════════════════════════════════════════════════════════════════
1. Your ENTIRE output must be the HTML document. Nothing else. No ```html.
2. The #1 VALUE of this report is showing HOW AND WHY prompts connect:
   - The transition triggers between steps are ESSENTIAL — never skip them.
   - Each step's "Intent" must explain what prior context led to this prompt.
   - The narrative should read as a coherent story, not a list of events.
3. Be DETAILED, not high-level. Include specific file names, function names,
   error messages, and concrete outcomes. The user wants to remember exactly
   what happened, not just a vague summary.
4. Make it VISUALLY STUNNING. This is a tool people open in their browser and
   should feel proud to show others.
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

