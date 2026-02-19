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

def get_bedrock_model_id(user_model_name: str) -> str:
    """Maps user-friendly model names to AWS Bedrock Model IDs."""
    # Normalize input
    name = user_model_name.lower()
    
    # Bedrock Model Map (Updated Feb 2026)
    mapping = {
        "opus": "anthropic.claude-3-opus-20240229-v1:0",
        "sonnet": "anthropic.claude-3-5-sonnet-20240620-v1:0", # Default 'sonnet' to 3.5
        "sonnet-3-5": "anthropic.claude-3-5-sonnet-20240620-v1:0",
        "haiku": "anthropic.claude-3-haiku-20240307-v1:0",
        "haiku-3-5": "anthropic.claude-3-5-haiku-20241022-v1:0",
    }
    
    # Direct match or partial match logic
    if name in mapping:
        return mapping[name]
        
    # Heuristic fallback for Bedrock IDs
    if "anthropic" in name:
        return name
        
    # Default to the most capable model if unsure (User preference)
    return "anthropic.claude-3-5-sonnet-20240620-v1:0"

def generate_summary(transcript: str, api_key: str, model: str = None, base_url: str = None) -> str:
    """Calls the LLM to analyze the session, attempting to match the user's chosen model."""
    
    # Defaults if not specified
    target_model = model or "gpt-4o" 
    
    system_prompt = """
    You are "ContextMap". Your job is to analyze a terminal session transcript...
    [Rest of prompt truncated for brevity]
    """
    
    user_prompt = f"Here is the session transcript. Analyze it:\n\n{transcript[-100000:]}"

    # --- AWS Bedrock Logic ---
    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        try:
            import boto3
            bedrock = boto3.client(service_name='bedrock-runtime', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            
            # Map the CLI model name to Bedrock ID
            bedrock_model_id = get_bedrock_model_id(target_model)
            
            # Claude 3/3.5 Message API Payload
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}]
            }
            
            response = bedrock.invoke_model(
                modelId=bedrock_model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload)
            )
            
            response_body = json.loads(response.get('body').read())
            return response_body.get('content')[0].get('text')
            
        except Exception as e:
            return f"❌ AWS Bedrock Error ({bedrock_model_id}): {str(e)}"

    # --- OpenAI / Anthropic via Adapter Logic ---
    # If the user passed a 'claude' model but we are using OpenAI client, 
    # we assume they might be using OpenRouter or similar, OR we fallback to GPT-4o
    # if standard OpenAI key is detected.
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    # Heuristic: If looking for Claude but using OpenAI Key -> warn or fallback?
    # For now, pass it through. Many proxies accept 'claude-3-opus' directly.
    
    try:
        response = client.chat.completions.create(
            model=target_model,
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
    parser = argparse.ArgumentParser(description="ContextMap Analyzer")
    parser.add_argument("log_file", help="Path to the raw session log")
    parser.add_argument("--out", default=".context/session_summary.md", help="Output path for summary")
    parser.add_argument("--model", default=None, help="The model used in the session")
    args = parser.parse_args()
    
    # ... [Rest of main]
    
    summary = generate_summary(transcript, api_key, model=args.model)

