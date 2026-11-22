import streamlit as st
import os
from html import escape
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

g = get_github_client(token)

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
def text_to_html_paragraphs(text):
    """Convert plain text with blank line separators into HTML paragraphs."""
    paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    return "\n\n".join(f"<p>{p}</p>" for p in paragraphs)

def wording_input(location):
    has_bullets = st.radio(
        "Does this wording update include bullet points?",
        ["No", "Yes"],
        key=f"{location}_has_bullets",
        horizontal=True,
    )
    if has_bullets == "No":
        return text_to_html_paragraphs(st.text_area(f"{location} wording", height=250))

    before = st.text_area("Before bullets", key=f"{location}_before_bullets")
    bullets = st.text_area(
        "Bullets",
        key=f"{location}_bullets",
        help="Paste one item per line without the bullet symbols.",
        placeholder="Paste one item per line without the bullet symbols.",
    )
    after = st.text_area("After bullets", key=f"{location}_after_bullets")

    items = [line.strip() for line in bullets.splitlines() if line.strip()]
    if not items:
        return ""

    list_html = "\n".join(["<ul>", *(f"  <li>{escape(item)}</li>" for item in items), "</ul>"])
    sections = [text_to_html_paragraphs(before), list_html, text_to_html_paragraphs(after)]
    return "\n\n".join(section for section in sections if section)

if operation == "Wording updates":
    st.header("Wording Updates")

    scope = st.radio(
        "Which wording to update?",
        ["Denver only", "WSlope only", "Both Denver & WSlope"]
    )

    locations = ["Denver", "WSlope"] if scope == "Both Denver & WSlope" else [scope.split()[0]]
    wording_by_location = {}
    for location in locations:
        if len(locations) > 1:
            st.subheader(location)
        wording_by_location[location] = wording_input(location)

    confirm = st.checkbox("Confirm wording overwrite")

    if st.button("Run wording update"):
        if not confirm:
            st.warning("Confirmation required")
            st.stop()
    
        for location, wording in wording_by_location.items():
            if not wording:
                st.warning(f"Enter wording for {location}. If bullet points are enabled, enter at least one bullet.")
                st.stop()
    
        if scope == "Both Denver & WSlope":
            source_files = list_text_files_in_folder(repo, "base_templates")
        else:
            source_files = list_text_files_in_folder(repo, "updated_letters")
    
        results = []
        for f in source_files:
            text, _ = read_file_contents(repo, f.path)
    
            for location, wording in wording_by_location.items():
                tag = location.lower()
                text = safe_replace_between_tags(
                    text,
                    f"<!-- {tag} wording start -->",
                    f"<!-- {tag} wording end -->",
                    wording
                )

            target = f"updated_letters/{f.name}"
            action = write_or_update_file(
                repo,
                target,
                text,
                f"Wording update ({scope})",
                BRANCH
            )
            results.append({"file": f.name, "action": action})

        st.success("Wording updates complete")
        st.dataframe(results)

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
