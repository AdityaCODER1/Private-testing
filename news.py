import os
from datetime import datetime, timezone
from google import genai

# 1. Load Gemini Secret Key (set in GitHub Actions Secrets as GEMINI_API_KEY)
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY environment variable is missing!")

client = genai.Client(api_key=api_key)

# 2. Model Configuration (Gemma 4 31B Instruct on Google Gemini API)
MODEL_NAME = "gemma-4-31b-it"


def call_model(prompt):
    print(f"Sending test prompt to {MODEL_NAME}...")
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )
    print(f"Response received from {MODEL_NAME}!")
    return response.text.strip()


def build_website_html(ai_output):
    now_str = datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Model Test | Hello World</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f1115;
            color: #f3f4f6;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }}
        .card {{
            background: #181b22;
            border: 1px solid #2a2f3d;
            border-radius: 14px;
            max-width: 600px;
            width: 100%;
            padding: 32px;
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.35);
        }}
        .badge {{
            display: inline-block;
            background: #ff4c00;
            color: #ffffff;
            font-size: 12px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 999px;
            margin-bottom: 14px;
        }}
        h1 {{
            margin: 0 0 12px;
            font-size: 28px;
        }}
        .output {{
            background: #101318;
            border: 1px solid #262b38;
            border-radius: 10px;
            padding: 16px;
            font-size: 16px;
            line-height: 1.6;
            white-space: pre-wrap;
            margin: 18px 0;
        }}
        .meta {{
            color: #9ca3af;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <main class="card">
        <span class="badge">Model: {MODEL_NAME}</span>
        <h1>Hello World</h1>
        <div class="output">{ai_output}</div>
        <div class="meta">Last built: {now_str}</div>
    </main>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Generated index.html successfully!")


if __name__ == "__main__":
    test_prompt = "Say 'Hello World!' and briefly confirm you are Gemma 4 31B running via the API."
    reply = call_model(test_prompt)
    build_website_html(reply)
