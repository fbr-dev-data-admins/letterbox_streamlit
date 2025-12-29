# github_helpers.py
from github import Github
import base64
import json
import re

# -----------------------------------------
# Get GitHub client
# -----------------------------------------
def get_github_client(token: str):
    if not token:
        raise ValueError("GitHub token required")
    return Github(token)

# -----------------------------------------
# List text or markdown files from a folder
# -----------------------------------------
def list_text_files_in_folder(repo, folder_path):
    """
    Returns a list of ContentFile objects representing text-like files in the folder.
    """
    try:
        contents = repo.get_contents(folder_path)
    except Exception:
        return []

    files = []
    for c in contents:
        if c.type == "file" and (
            c.name.endswith(".txt") or 
            c.name.endswith(".md") or 
            c.name.endswith(".html")
        ):
            files.append(c)
    return files

# -----------------------------------------
# Read file contents
# -----------------------------------------
def read_file_contents(repo, path):
    """
    Returns (decoded_text, sha)
    """
    c = repo.get_contents(path)
    decoded = base64.b64decode(c.content).decode("utf-8")
    return decoded, c.sha

# -----------------------------------------
# Replace between tags (safe)
# -----------------------------------------
def safe_replace_between_tags(text, start_tag, end_tag, replacement):
    """
    Replace exactly the block between start_tag and end_tag (inclusive of those tags)
    with:
        start_tag + "\n" + replacement + "\n" + end_tag
    """
    pattern = re.escape(start_tag) + r"(.*?)" + re.escape(end_tag)
    repl = start_tag + "\n" + replacement + "\n" + end_tag

    new_text, n = re.subn(pattern, repl, text, flags=re.DOTALL)

    if n == 0:
        raise ValueError(f"Tags not found: {start_tag}, {end_tag}")

    return new_text

# -----------------------------------------
# Write or update file in repo
# -----------------------------------------
def write_or_update_file(repo, path, content, commit_message="Updated file", branch="main"):
    """
    If file exists -> update; if not -> create.
    """
    try:
        existing = repo.get_contents(path, ref=branch)
        return repo.update_file(
            path, commit_message, content, existing.sha, branch=branch
        )
    except Exception:
        # create
        return repo.create_file(
            path, commit_message, content, branch=branch
        )

# -----------------------------------------
# Load JSON file from repo
# -----------------------------------------
def get_json_from_repo(repo, path):
    """
    Loads and returns (json_dict, sha)
    """
    c = repo.get_contents(path)
    decoded = base64.b64decode(c.content).decode("utf-8")
    return json.loads(decoded), c.sha
