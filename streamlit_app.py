import streamlit as st
import os
from github_helpers import *

st.set_page_config(page_title="Letterbox", layout="wide")
st.title("Letterbox — Template Updater")

# ---------------- Token resolution ----------------
def resolve_token():
    if st.secrets.get("GITHUB_TOKEN"):
        return st.secrets["GITHUB_TOKEN"]
    if os.getenv("GITHUB_TOKEN"):
        return os.getenv("GITHUB_TOKEN")
    try:
        return keyring.get_password("github", "github_token")
    except Exception:
        return None

token = resolve_token()
if not token:
    st.error("GitHub token not found.")
    st.stop()

g = get_github_client(token)

# ---------------- Repo config ----------------
st.sidebar.header("Private Repo")
owner = st.sidebar.text_input("Owner")
repo_name = st.sidebar.text_input("Repo name")
branch = st.sidebar.text_input("Branch", value="main")

if not owner or not repo_name:
    st.stop()

repo = g.get_repo(f"{owner}/{repo_name}")

operation = st.radio("Operation", ["Wording updates", "Signature updates"])

# ==================================================
# WORDING UPDATES
# ==================================================
if operation == "Wording updates":
    st.header("Wording Updates")

    scope = st.radio(
        "Which wording to update?",
        ["Denver only", "WSlope only", "Both Denver & WSlope"]
    )

    denver_text = ""
    wslope_text = ""

    if scope in ("Denver only", "Both Denver & WSlope"):
        denver_text = st.text_area("Denver wording", height=250)

    if scope in ("WSlope only", "Both Denver & WSlope"):
        wslope_text = st.text_area("WSlope wording", height=250)

    confirm = st.checkbox("Confirm wording overwrite")

    if st.button("Run wording update"):
        if not confirm:
            st.warning("Confirmation required")
            st.stop()

        # Source logic
        if scope == "Both Denver & WSlope":
            source_files = list_text_files_in_folder(repo, "base_templates")
        else:
            source_files = list_text_files_in_folder(repo, "updated_letters")

        results = []
        for f in source_files:
            text, _ = read_file_contents(repo, f.path)

            if scope in ("Denver only", "Both Denver & WSlope"):
                text = safe_replace_between_tags(
                    text,
                    "<!-- denver wording start -->",
                    "<!-- denver wording end -->",
                    denver_text
                )

            if scope in ("WSlope only", "Both Denver & WSlope"):
                text = safe_replace_between_tags(
                    text,
                    "<!-- wslope wording start -->",
                    "<!-- wslope wording end -->",
                    wslope_text
                )

            target = f"updated_letters/{f.name}"
            action = write_or_update_file(
                repo,
                target,
                text,
                f"Wording update ({scope})",
                branch
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
                branch
            )
            results.append({"file": f.name, "action": action})

        st.success("Signature updates complete")
        st.dataframe(results)
