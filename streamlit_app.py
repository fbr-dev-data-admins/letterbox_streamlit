import streamlit as st
import os
import re
from github_helpers import *
try:
    import keyring
except ImportError:
    keyring = None

st.set_page_config(page_title="Letterbox", layout="wide")
st.title("Letterbox — Template Updater")

# ---------------- Token resolution ----------------
def resolve_token():
    # Streamlit Cloud
    if "GITHUB_TOKEN" in st.secrets:
        return st.secrets["GITHUB_TOKEN"]

    # Local env var
    if os.getenv("GITHUB_TOKEN"):
        return os.getenv("GITHUB_TOKEN")

    # Optional: local keyring only
    if keyring:
        try:
            return keyring.get_password("github", "github_token")
        except Exception:
            pass

    return None

token = resolve_token()
if not token:
    st.error("GitHub token not found.")
    st.stop()

g = get_github_client(token)

# ---------------- Repo configuration (from secrets) ----------------
try:
    REPO_OWNER = st.secrets["GITHUB_REPO_OWNER"]
    REPO_NAME = st.secrets["GITHUB_REPO_NAME"]
    BRANCH = st.secrets.get("GITHUB_REPO_BRANCH", "main")
except KeyError as e:
    st.error(f"Missing required secret: {e}")
    st.stop()

try:
    repo = g.get_repo(f"{REPO_OWNER}/{REPO_NAME}")
except Exception as e:
    st.error(f"Unable to access private repo: {e}")
    st.stop()

st.caption(f"Connected to private repo: `{REPO_OWNER}/{REPO_NAME}` on branch `{BRANCH}`")

operation = st.selectbox(
    "What would you like to update?",
    ["Wording updates", "Signature updates"]
)
# ==================================================
# WORDING UPDATES
# ==================================================
_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
_NUMBER = re.compile(r"^\s*\d+[.)]\s+(.*)$")

def text_to_html_paragraphs(text):
    """Plain text -> HTML. Blank lines separate paragraphs;
    lines starting with -, *, or • become <ul>; lines starting with 1. or 1) become <ol>."""
    blocks = []  # (kind, [lines])

    def add(kind, line):
        if blocks and blocks[-1][0] == kind and not blocks[-1][2]:
            blocks[-1][1].append(line)
        else:
            blocks.append((kind, [line], False))

    closed = True
    for raw in text.strip().splitlines():
        b, n = _BULLET.match(raw), _NUMBER.match(raw)
        if b or n:
            kind = "ul" if b else "ol"
            if blocks and blocks[-1][0] == kind and not closed:
                blocks[-1][1].append((b or n).group(1).strip())
            else:
                blocks.append((kind, [(b or n).group(1).strip()], False))
            closed = False
        elif not raw.strip():
            closed = True
        else:
            if blocks and blocks[-1][0] == "p" and not closed:
                blocks[-1][1].append(raw.strip())
            else:
                blocks.append(("p", [raw.strip()], False))
            closed = False

    out = []
    for kind, lines, _ in blocks:
        if kind == "p":
            out.append("<p>" + "\n".join(lines) + "</p>")
        else:
            items = "\n".join(f"  <li>{l}</li>" for l in lines)
            out.append(f"<{kind}>\n{items}\n</{kind}>")
    return "\n\n".join(out)

# ==================================================
# SIGNATURE UPDATES
# ==================================================
else:
    st.header("Signature Updates")

    config, _ = get_json_from_repo(repo, "config/signatures.json")

    location = st.selectbox("Location", ["Denver", "WSlope"])
    loc_key = location.lower()

    sets = list(config.get(loc_key, {}).keys())
    selected_set = st.selectbox("Signature set", ["Custom"] + sets)

    tiers = []

    if selected_set != "Custom":
        tiers = config[loc_key][selected_set]
    else:
        st.info("Custom signees (max 4)")
        count = st.number_input("How many signees?", 1, 4, 1)
        for i in range(int(count)):
            st.subheader(f"Signee {i+1}")
            tiers.append({
                "name": st.text_input("Name", key=f"n{i}"),
                "title": st.text_input("Title", key=f"t{i}"),
                "min_gift": st.number_input("Min gift (inclusive)", 0.0, key=f"m{i}")
            })

    tiers = sorted(tiers, key=lambda x: x["min_gift"], reverse=True)

    def build_snippet(tiers):
        out = []
        for i, t in enumerate(tiers):
            compare_val = f"{t['min_gift'] - 0.01:.2f}"
            if i < len(tiers) - 1:
                out.append(f'{{{{#if (compare Gift.amount.value ">" {compare_val})}}}}')
            out.append("<p>")
            out.append(t["name"])
            out.append("<br>")
            out.append(t["title"])
            out.append("</p>")
            if i < len(tiers) - 1:
                out.append("{{else}}")
        out.extend(["{{/if}}"] * (len(tiers) - 1))
        return "\n".join(out)

    snippet = build_snippet(tiers)
    st.code(snippet)

    confirm = st.checkbox("Confirm signature overwrite")

    if st.button("Run signature update"):
        if not confirm:
            st.stop()

        files = [
            f for f in list_text_files_in_folder(repo, "updated_letters")
            if f.name.lower().endswith("_live.txt")
        ]

        results = []
        for f in files:
            text, _ = read_file_contents(repo, f.path)
            start = f"<!-- {loc_key} sig start -->"
            end = f"<!-- {loc_key} sig end -->"

            text = safe_replace_between_tags(text, start, end, snippet)
            action = write_or_update_file(
                repo,
                f.path,
                text,
                f"Signature update ({location})",
                BRANCH
            )
            results.append({"file": f.name, "action": action})

        st.success("Signature updates complete")
        st.dataframe(results)
