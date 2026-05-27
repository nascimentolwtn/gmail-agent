"""Helper to extract project_id from credentials.json and derive namespaced filenames."""

import json
import os
from pathlib import Path


def get_project_id() -> str:
    """Extract project_id from credentials.json. Returns empty string if not found."""
    credentials_path = "credentials.json"
    if not os.path.exists(credentials_path):
        return ""

    try:
        with open(credentials_path, "r", encoding="utf-8") as f:
            creds = json.load(f)
        # Handle both "installed" and "web" OAuth types
        if "installed" in creds:
            return creds["installed"].get("project_id", "")
        if "web" in creds:
            return creds["web"].get("project_id", "")
        return creds.get("project_id", "")
    except (json.JSONDecodeError, IOError):
        return ""


def get_examples_filename() -> str:
    """Return the filename for examples, namespaced by project_id if available."""
    project_id = get_project_id()
    if project_id:
        return f"examples_{project_id}.json"
    return "examples.json"


def get_pending_suggestions_filename() -> str:
    """Return the filename for pending suggestions, namespaced by project_id if available."""
    project_id = get_project_id()
    if project_id:
        return f"pending_suggestions_{project_id}.json"
    return "pending_suggestions.json"


def migrate_examples_on_first_run() -> None:
    """
    If old examples.json exists but namespaced examples_{project_id}.json doesn't,
    copy it. This preserves training data when migrating to per-credential setup.
    """
    project_id = get_project_id()
    if not project_id:
        return  # No project_id, can't migrate

    old_file = "examples.json"
    new_file = f"examples_{project_id}.json"

    # Only migrate if old exists and new doesn't
    if os.path.exists(old_file) and not os.path.exists(new_file):
        try:
            with open(old_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            with open(new_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"✓ Migrated {old_file} → {new_file}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"✗ Failed to migrate examples: {e}")

    # Same for pending_suggestions
    old_pending = "pending_suggestions.json"
    new_pending = f"pending_suggestions_{project_id}.json"

    if os.path.exists(old_pending) and not os.path.exists(new_pending):
        try:
            with open(old_pending, "r", encoding="utf-8") as f:
                data = json.load(f)
            with open(new_pending, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"✓ Migrated {old_pending} → {new_pending}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"✗ Failed to migrate pending suggestions: {e}")
