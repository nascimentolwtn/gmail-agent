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

    return f"""You are an email categorization assistant. Your job is to suggest actions for incoming emails based on the user's past decisions.

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
    """Ask local LLM to suggest an action for a single email."""
    system_prompt = build_system_prompt(examples, label_map)

    user_message = f"""Suggest an action for this email:

From: {email['from']}
Subject: {email['subject']}
Date: {email['date']}

Reply with JSON only."""

    payload = {
        "model": "local",
        "max_tokens": 100,
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
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        # debug: uncomment if still failing
        # import pprint; pprint.pprint(data)

        # extract text — handle Anthropic and OpenAI response formats
        raw = None
        # extract text — Anthropic format
        if "content" in data:
            content = data["content"]
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        # try "text" key directly (some llama.cpp versions)
                        if "text" in block:
                            raw = block["text"]
                            break
                        # standard Anthropic type/text block
                        elif block.get("type") == "text":
                            raw = block["text"]
                            break
                    elif isinstance(block, str):
                        raw = block
                        break
            elif isinstance(content, str):
                raw = content

        elif "choices" in data:
            raw = data["choices"][0]["message"]["content"]

        if raw is None:
            # last resort debug — print full first content block
            import pprint
            pprint.pprint(data.get("content"))
            return {"action": None, "error": "could not extract text"}

        elif "choices" in data:
            # OpenAI format: {"choices": [{"message": {"content": "..."}}]}
            raw = data["choices"][0]["message"]["content"]

        if raw is None:
            return {"action": None, "error": f"unrecognized response format: {list(data.keys())}"}

        raw = raw.strip()

        # strip markdown fences if model adds them
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        suggestion = json.loads(raw)
        return suggestion

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