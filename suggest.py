import json
import requests

LLAMA_URL = "http://localhost:11434/v1/messages"
EXAMPLES_FILE = "examples.json"

def load_examples():
    with open(EXAMPLES_FILE, "r") as f:
        return json.load(f)

def build_system_prompt(examples, label_map):
    """Build system prompt with examples and available labels."""
    labels_list = ", ".join(label_map.keys())

    # pick up to 40 most recent examples to keep prompt size reasonable
    recent = examples[-40:]
    examples_text = json.dumps(recent, ensure_ascii=False, indent=2)
    return f"""/no_think
        You are an email categorization assistant. Your job is to suggest actions for incoming emails based on the user's past decisions.

AVAILABLE LABELS (use exactly these names):
{labels_list}

PAST DECISIONS (learn the user's pattern from these):
{examples_text}

RULES:
- Suggest either "delete" OR one or more labels from the available list
- Never invent label names — only use labels from the list above
- Return ONLY valid JSON, no explanation, no markdown
- Format: {{"action": "delete"}} OR {{"action": ["tag:LabelName", "tag:OtherLabel"]}}
- When uncertain between delete and tag, prefer tag
"""

def suggest_action(email, examples, label_map):
    system_prompt = build_system_prompt(examples, label_map)

    user_message = f"""/no_think Suggest an action for this email and reply with JSON only.

From: {email['from']}
Subject: {email['subject']}
Date: {email['date']}"""

    payload = {
        "model": "local",
        "max_tokens": 2048,        # enough for thinking + text block
        "thinking": {"type": "disabled"},   # llama.cpp flag — ignored if unsupported
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_message}
        ]
    }

    try:
        response = requests.post(
            LLAMA_URL,
            json=payload,
            headers={"x-api-key": "local"},
            timeout=60        # more time for thinking models
        )
        response.raise_for_status()
        data = response.json()

        raw = None
        if "content" in data:
            content = data["content"]
            if isinstance(content, list):
                # first pass: look for explicit text block
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text" and "text" in block:
                            raw = block["text"]
                            break
                # second pass: any block with a text key (not thinking)
                if raw is None:
                    for block in content:
                        if isinstance(block, dict) and block.get("type") != "thinking":
                            if "text" in block:
                                raw = block["text"]
                                break
                # debug: show full content if still nothing
                if raw is None:
                    import pprint
                    print("\n  [DEBUG] Full content blocks:")
                    pprint.pprint(content)
            elif isinstance(content, str):
                raw = content
        elif "choices" in data:
            raw = data["choices"][0]["message"]["content"]

        if raw is None:
            return {"action": None, "error": "no text block in response"}

        raw = raw.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        return json.loads(raw)

    except requests.exceptions.Timeout:
        return {"action": None, "error": "timeout"}
    except json.JSONDecodeError:
        return {"action": None, "error": f"bad json: {raw}"}
    except Exception as e:
        return {"action": None, "error": str(e)}

def format_suggestion(suggestion):
    """Human-readable suggestion string."""
    action = suggestion.get("action")
    if action is None:
        return f"⚠ LLM error: {suggestion.get('error', 'unknown')}"
    if action == "delete":
        return "🗑  delete"
    if isinstance(action, list):
        labels = ", ".join(a.replace("tag:", "") for a in action)
        return f"🏷  {labels}"
    return f"? {action}"