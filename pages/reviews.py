"""
Review Moderation Tool
======================
Usage:
  1. pip install streamlit pandas openpyxl
  2. streamlit run review_moderator.py

Expects:
  - A CSV of reviews (same format as rating_reviews_*.csv)
  - Optionally: a plain-text file of vulgar words (one per line), e.g. vulgar_words.txt

Auto-rejection rules are based on the Ratings & Review Approval Guidelines.
"""

import streamlit as st
import pandas as pd
import re
import os
import json
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Review Moderator",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    .flag-tag {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
        margin: 2px 3px;
    }
    .flag-reject   { background:#fde8e8; color:#b91c1c; }
    .flag-escalate { background:#fef3c7; color:#b45309; }
    .flag-edit     { background:#dbeafe; color:#1d4ed8; }
    .flag-delete   { background:#f3e8ff; color:#7e22ce; }
    .review-card {
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 10px;
        background: #fff;
    }
    .review-card.auto-reject { border-left: 4px solid #ef4444; }
    .review-card.manual      { border-left: 4px solid #6b7280; }
    div[data-testid="stMetricValue"] { font-size: 28px !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# GUIDELINE AUTO-REJECTION RULES
# ─────────────────────────────────────────────

PHONE_PATTERN = re.compile(r'(?<!\d)(0[17]\d{8,9}|\+\d{9,13})(?!\d)')
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')

# Words / phrases that flag delivery-only (not product) content
DELIVERY_ONLY_PHRASES = [
    "delivery was fast", "delivered on time", "delivery agent",
    "customer care", "j-force", "pickup station agent",
    "placed my order through agent", "place your order through agent",
    "place your orders through agent", "order through agent",
    "delivered to my work place", "delivered to uasin gishu",
    "for faster deliver",
]

# Social media / third-party channel mentions
SOCIAL_MEDIA_PATTERNS = re.compile(
    r'\b(whatsapp|telegram|instagram|tiktok|facebook|twitter|youtube|snapchat)\b',
    re.IGNORECASE
)

# Positive sentiment words used for mismatch detection
POSITIVE_WORDS = [
    "excellent", "amazing", "love it", "great product", "perfect", "awesome",
    "superb", "fantastic", "best", "wonderful", "highly recommend",
]
NEGATIVE_WORDS = [
    "terrible", "horrible", "worst", "hate it", "dangerous", "fake",
    "scam", "rubbish", "awful", "disgusting", "not good", "very poor",
    "fraud", "counterfeit", "not original", "totally useless",
]

# Known-bad agent number for spam detection
KNOWN_SPAM_PATTERNS = ["0799370803"]

# Languages that are NOT English or Nigerian Pidgin — very basic heuristic
# (flags words/phrases that look like Swahili, French, etc.)
NON_ENGLISH_PATTERNS = re.compile(
    r'\b(na|iko|poa|merci|bonjour|très|gut|danke|bueno|gracias|muito|obrigado|سلام|谢谢|شكرا)\b',
    re.IGNORECASE
)


def load_vulgar_words(filepath: str) -> list[str]:
    """Load vulgar words from a plain-text file (one word/phrase per line)."""
    if not filepath or not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return [line.strip().lower() for line in f if line.strip()]


def check_review(row: pd.Series, vulgar_words: list[str]) -> dict:
    """
    Apply all guideline rules to a single review row.
    Returns a dict with:
      - flags: list of (label, severity) tuples  [severity: reject|escalate|edit|delete]
      - auto_action: 'REJECT' | 'DELETE' | 'ESCALATE' | 'APPROVE' | 'MANUAL'
      - reason_summary: short human-readable summary
    """
    flags = []
    title = str(row.get("Review Title", "")).strip()
    text  = str(row.get("Review Detail Text", "")).strip()
    combined = (title + " " + text).lower()
    rating = int(row.get("Rating", 3))

    # ── Guideline 2: Contact details ──────────────────────────────────────
    if PHONE_PATTERN.search(combined):
        flags.append(("Phone number found", "reject"))
    if EMAIL_PATTERN.search(combined):
        flags.append(("Email address found", "reject"))

    # ── Guideline 7 & 2: Known spam / agent promotion ──────────────────────
    for sp in KNOWN_SPAM_PATTERNS:
        if sp in combined:
            flags.append((f"Spam — agent promotion ({sp})", "delete"))

    # ── Guideline 1: About delivery, not product ──────────────────────────
    delivery_hits = [p for p in DELIVERY_ONLY_PHRASES if p in combined]
    if delivery_hits and len(text) < 120:
        flags.append(("Delivery-only comment, not about product", "edit"))

    # ── Guideline 6: Language check ───────────────────────────────────────
    if NON_ENGLISH_PATTERNS.search(combined):
        flags.append(("Non-English / non-pidgin language detected", "reject"))

    # ── Guideline 9: Social media mentions ───────────────────────────────
    if SOCIAL_MEDIA_PATTERNS.search(combined):
        flags.append(("Social media channel mentioned", "edit"))

    # ── Guideline 10: Rating mismatch ─────────────────────────────────────
    if rating == 5 and any(w in combined for w in NEGATIVE_WORDS):
        flags.append(("5★ but content is negative", "reject"))
    if rating == 1 and any(w in combined for w in POSITIVE_WORDS):
        flags.append(("1★ but content is positive", "reject"))

    # ── Safety / dangerous product ────────────────────────────────────────
    safety_kw = ["burn", "electrocute", "dangerous", "fire", "burned my house",
                 "unsafe", "nearly burned", "short circuit", "explosion", "exploded",
                 "caught fire", "smoke", "sparks", "shocked"]
    if any(k in combined for k in safety_kw) and rating <= 2:
        flags.append(("Safety hazard reported — escalate to safety team", "escalate"))

    # ── Guideline 4 & 5: Fake / counterfeit / not as described ───────────
    fake_kw = ["fake", "counterfeit", "not original", "not authentic",
               "not as described", "not what i ordered", "wrong item",
               "wrong colour", "wrong color", "wrong size",
               "specs are not same", "validation qr"]
    if any(k in combined for k in fake_kw) and rating <= 2:
        flags.append(("Fake/counterfeit or not-as-described — escalate to VXP", "escalate"))

    # ── Vulgar words ──────────────────────────────────────────────────────
    for vw in vulgar_words:
        if vw in combined:
            flags.append((f'Vulgar word: "{vw}"', "reject"))
            break  # one flag is enough

    # ── Determine auto_action ─────────────────────────────────────────────
    severities = [sev for _, sev in flags]
    if "delete" in severities:
        auto_action = "DELETE"
    elif "reject" in severities:
        auto_action = "REJECT"
    elif "escalate" in severities:
        auto_action = "ESCALATE"
    elif "edit" in severities:
        auto_action = "MANUAL"   # needs human review
    else:
        auto_action = "APPROVE"

    reason_summary = "; ".join(label for label, _ in flags) if flags else "No issues found"
    return {"flags": flags, "auto_action": auto_action, "reason_summary": reason_summary}


# ─────────────────────────────────────────────
# SESSION STATE HELPERS
# ─────────────────────────────────────────────

def init_state():
    if "decisions" not in st.session_state:
        st.session_state.decisions = {}   # review_id -> 'APPROVED' | 'REJECTED' | 'ESCALATED' | 'DELETED' | 'PENDING'
    if "notes" not in st.session_state:
        st.session_state.notes = {}        # review_id -> str
    if "filter_tab" not in st.session_state:
        st.session_state.filter_tab = "All"


def get_decision(rid):
    return st.session_state.decisions.get(str(rid), "PENDING")


def set_decision(rid, decision):
    st.session_state.decisions[str(rid)] = decision


# ─────────────────────────────────────────────
# SIDEBAR — FILE UPLOAD & SETTINGS
# ─────────────────────────────────────────────

def sidebar():
    st.sidebar.image("https://via.placeholder.com/180x40?text=Review+Moderator", use_container_width=True)
    st.sidebar.markdown("---")

    st.sidebar.header("📂 Load files")
    csv_file    = st.sidebar.file_uploader("Reviews CSV", type=["csv"])
    vulgar_file = st.sidebar.file_uploader("Vulgar words list (optional, .txt)", type=["txt"])

    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Settings")
    auto_apply = st.sidebar.toggle("Auto-apply decisions on load", value=True,
                                   help="Automatically mark auto-detectable reviews as REJECT/DELETE/ESCALATE when you upload")
    show_approved = st.sidebar.toggle("Show APPROVED in queue", value=False)

    st.sidebar.markdown("---")
    st.sidebar.caption("Guidelines: Ratings & Review Approval Guidelines v1")

    return csv_file, vulgar_file, auto_apply, show_approved


# ─────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────

def main():
    init_state()
    csv_file, vulgar_file, auto_apply, show_approved = sidebar()

    st.title("🛡️ Review Moderation Tool")
    st.caption("Powered by Jumia Ratings & Review Approval Guidelines")

    if csv_file is None:
        st.info("👈 Upload a reviews CSV in the sidebar to get started.")
        st.markdown("""
        **Expected CSV columns:**
        `ID, Review Title, Review Detail Text, Customer Nickname, Customer Email, SKU, Seller Name, Status, Created Date, Updated Date, Rating`
        
        **Optional:** upload a `vulgar_words.txt` file with one word/phrase per line to auto-flag profanity.
        """)
        return

    # ── Load data ─────────────────────────────────────────────────────────
    df = pd.read_csv(csv_file, dtype=str)
    df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce").fillna(3).astype(int)
    df["ID"] = df["ID"].astype(str)

    # Load vulgar words — from uploaded file OR auto-load from app root
    vulgar_words = []
    if vulgar_file is not None:
        content = vulgar_file.read().decode("utf-8", errors="ignore")
        vulgar_words = [line.strip().lower() for line in content.splitlines()
                        if line.strip() and not line.strip().startswith("#")]
    else:
        # Auto-load from app root directory (same folder as review_moderator.py)
        app_root = Path(__file__).parent
        for candidate in ["vulgar_words_template.txt", "vulgar_words.txt"]:
            auto_path = app_root / candidate
            if auto_path.exists():
                with open(auto_path, "r", encoding="utf-8", errors="ignore") as f:
                    vulgar_words = [line.strip().lower() for line in f
                                    if line.strip() and not line.strip().startswith("#")]
                st.sidebar.success(f"✅ Loaded {len(vulgar_words)} vulgar words from `{candidate}`")
                break

    # ── Run auto-detection ────────────────────────────────────────────────
    analysis = {}
    for _, row in df.iterrows():
        analysis[row["ID"]] = check_review(row, vulgar_words)

    # Auto-apply decisions on first load
    if auto_apply:
        for rid, result in analysis.items():
            if get_decision(rid) == "PENDING":
                if result["auto_action"] in ("REJECT", "DELETE", "ESCALATE"):
                    set_decision(rid, result["auto_action"])

    # Detect duplicates (same email + SKU)
    dup_map = {}
    if "Customer Email" in df.columns and "SKU" in df.columns:
        df["_key"] = df["Customer Email"].str.lower() + "||" + df["SKU"].str.upper()
        key_counts = df.groupby("_key")["ID"].apply(list).to_dict()
        for key, ids in key_counts.items():
            if len(ids) > 1:
                for rid in ids:
                    dup_map[str(rid)] = ids

    # ── Summary metrics ────────────────────────────────────────────────────
    total     = len(df)
    n_pending  = sum(1 for r in df["ID"] if get_decision(r) == "PENDING")
    n_approved = sum(1 for r in df["ID"] if get_decision(r) == "APPROVED")
    n_rejected = sum(1 for r in df["ID"] if get_decision(r) in ("REJECTED","REJECT"))
    n_escalate = sum(1 for r in df["ID"] if get_decision(r) in ("ESCALATED","ESCALATE"))
    n_deleted  = sum(1 for r in df["ID"] if get_decision(r) in ("DELETED","DELETE"))
    n_auto_flagged = sum(1 for r in analysis.values() if r["auto_action"] != "APPROVE")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total",      total)
    c2.metric("Pending",    n_pending,  delta=f"-{total - n_pending} done", delta_color="inverse")
    c3.metric("Approved",   n_approved, delta_color="normal")
    c4.metric("Rejected",   n_rejected, delta_color="inverse")
    c5.metric("Escalated",  n_escalate, delta_color="off")
    c6.metric("Auto-flagged", n_auto_flagged, delta_color="inverse")

    st.markdown("---")

    # ── Tabs ────────────────────────────────────────────────────────────────
    tab_labels = ["🔴 Auto-flagged", "📋 All reviews", "📊 Analytics", "💾 Export"]
    tab1, tab2, tab3, tab4 = st.tabs(tab_labels)

    # ── TAB 1: Auto-flagged ─────────────────────────────────────────────────
    with tab1:
        flagged_ids = [row["ID"] for _, row in df.iterrows()
                       if analysis[row["ID"]]["auto_action"] != "APPROVE"]
        st.markdown(f"**{len(flagged_ids)} reviews auto-flagged** by guideline rules. Review and confirm below.")

        if not flagged_ids:
            st.success("🎉 No reviews were auto-flagged — queue is clean!")
        else:
            for _, row in df[df["ID"].isin(flagged_ids)].iterrows():
                render_review_card(row, analysis[row["ID"]], dup_map, tab_prefix="tab1")

    # ── TAB 2: All reviews ──────────────────────────────────────────────────
    with tab2:
        col_filter, col_search, col_sort = st.columns([2, 3, 2])
        status_filter = col_filter.selectbox(
            "Filter by status",
            ["All", "PENDING", "APPROVED", "REJECTED", "ESCALATED", "DELETED"],
        )
        search_query = col_search.text_input("Search title / text / seller / SKU", "")
        sort_by = col_sort.selectbox("Sort by", ["Newest first", "Oldest first", "Rating ↑", "Rating ↓"])

        filtered = df.copy()
        if status_filter != "All":
            filtered = filtered[filtered["ID"].apply(lambda r: get_decision(r).upper().startswith(status_filter))]
        if not show_approved:
            filtered = filtered[filtered["ID"].apply(lambda r: get_decision(r) != "APPROVED")]
        if search_query:
            q = search_query.lower()
            mask = (
                filtered["Review Title"].str.lower().str.contains(q, na=False) |
                filtered["Review Detail Text"].str.lower().str.contains(q, na=False) |
                filtered.get("Seller Name", pd.Series(dtype=str)).str.lower().str.contains(q, na=False) |
                filtered.get("SKU", pd.Series(dtype=str)).str.lower().str.contains(q, na=False)
            )
            filtered = filtered[mask]

        if sort_by == "Newest first":
            filtered = filtered.sort_values("Created Date", ascending=False, na_position="last")
        elif sort_by == "Oldest first":
            filtered = filtered.sort_values("Created Date", ascending=True, na_position="last")
        elif sort_by == "Rating ↑":
            filtered = filtered.sort_values("Rating", ascending=True)
        elif sort_by == "Rating ↓":
            filtered = filtered.sort_values("Rating", ascending=False)

        st.markdown(f"Showing **{len(filtered)}** reviews")

        # Bulk actions
        if len(filtered) > 0:
            bcol1, bcol2, bcol3, _ = st.columns([1,1,1,4])
            if bcol1.button("✅ Approve all visible", type="secondary"):
                for rid in filtered["ID"]:
                    set_decision(rid, "APPROVED")
                st.rerun()
            if bcol2.button("❌ Reject all visible", type="secondary"):
                for rid in filtered["ID"]:
                    set_decision(rid, "REJECTED")
                st.rerun()
            if bcol3.button("📤 Escalate all visible", type="secondary"):
                for rid in filtered["ID"]:
                    set_decision(rid, "ESCALATED")
                st.rerun()

        for _, row in filtered.iterrows():
            render_review_card(row, analysis[row["ID"]], dup_map, tab_prefix="tab2")

    # ── TAB 3: Analytics ────────────────────────────────────────────────────
    with tab3:
        st.subheader("Rating distribution")
        rating_counts = df["Rating"].value_counts().sort_index()
        st.bar_chart(rating_counts)

        st.subheader("Auto-flag breakdown")
        all_flags = []
        for result in analysis.values():
            for label, sev in result["flags"]:
                all_flags.append({"Flag": label, "Severity": sev})
        if all_flags:
            flag_df = pd.DataFrame(all_flags)
            st.dataframe(flag_df["Flag"].value_counts().rename("Count").reset_index(), use_container_width=True)

        if "Seller Name" in df.columns:
            st.subheader("Sellers with most flagged reviews")
            flagged_df = df[df["ID"].isin(flagged_ids)] if "flagged_ids" in dir() else df
            if "Seller Name" in flagged_df.columns:
                seller_flags = flagged_df["Seller Name"].value_counts().head(15)
                st.bar_chart(seller_flags)

            st.subheader("Sellers with lowest average rating (min 3 reviews)")
            seller_avg = (
                df.groupby("Seller Name")["Rating"]
                .agg(["mean", "count"])
                .query("count >= 3")
                .sort_values("mean")
                .head(15)
                .rename(columns={"mean": "Avg Rating", "count": "# Reviews"})
            )
            seller_avg["Avg Rating"] = seller_avg["Avg Rating"].round(2)
            st.dataframe(seller_avg, use_container_width=True)

    # ── TAB 4: Export ───────────────────────────────────────────────────────
    with tab4:
        st.subheader("Export moderated results")

        result_df = df.copy()
        result_df["Moderation Decision"] = result_df["ID"].apply(get_decision)
        result_df["Auto Flag Reason"]    = result_df["ID"].apply(lambda r: analysis[r]["reason_summary"])
        result_df["Moderation Note"]     = result_df["ID"].apply(lambda r: st.session_state.notes.get(r, ""))
        result_df["Moderated At"]        = datetime.now().strftime("%Y-%m-%d %H:%M")

        approved_df  = result_df[result_df["Moderation Decision"] == "APPROVED"]
        rejected_df  = result_df[result_df["Moderation Decision"].isin(["REJECTED", "REJECT"])]
        escalated_df = result_df[result_df["Moderation Decision"].isin(["ESCALATED", "ESCALATE"])]
        pending_df   = result_df[result_df["Moderation Decision"] == "PENDING"]

        st.markdown(f"""
        | Status | Count |
        |--------|-------|
        | ✅ Approved | {len(approved_df)} |
        | ❌ Rejected | {len(rejected_df)} |
        | 📤 Escalated | {len(escalated_df)} |
        | ⏳ Pending | {len(pending_df)} |
        """)

        ec1, ec2, ec3 = st.columns(3)

        csv_all = result_df.to_csv(index=False).encode("utf-8")
        ec1.download_button("⬇️ Download full results CSV", csv_all,
                            f"moderated_reviews_{datetime.now():%Y%m%d_%H%M}.csv", "text/csv")

        if len(approved_df) > 0:
            csv_app = approved_df.to_csv(index=False).encode("utf-8")
            ec2.download_button("✅ Download approved only", csv_app,
                                f"approved_reviews_{datetime.now():%Y%m%d_%H%M}.csv", "text/csv")

        if len(rejected_df) + len(escalated_df) > 0:
            issues_df = pd.concat([rejected_df, escalated_df, pending_df])
            csv_iss = issues_df.to_csv(index=False).encode("utf-8")
            ec3.download_button("⚠️ Download issues (rejected + escalated)", csv_iss,
                                f"issues_reviews_{datetime.now():%Y%m%d_%H%M}.csv", "text/csv")

        st.markdown("---")
        st.subheader("📋 Escalation report (copy/paste to email)")
        if len(escalated_df) > 0:
            report_lines = ["ESCALATION REPORT", f"Generated: {datetime.now():%Y-%m-%d %H:%M}", "="*60]
            for _, r in escalated_df.iterrows():
                report_lines += [
                    f"\nID: {r['ID']}  |  SKU: {r.get('SKU','')}  |  Seller: {r.get('Seller Name','')}",
                    f"Rating: {r['Rating']}★  |  Title: {r['Review Title']}",
                    f"Detail: {r['Review Detail Text'][:300]}",
                    f"Reason: {r['Auto Flag Reason']}",
                    "-"*40,
                ]
            st.text_area("Escalation report", "\n".join(report_lines), height=300)
        else:
            st.info("No escalated reviews yet.")


# ─────────────────────────────────────────────
# REVIEW CARD RENDERER
# ─────────────────────────────────────────────

FLAG_STYLE = {
    "reject":   "flag-reject",
    "delete":   "flag-delete",
    "escalate": "flag-escalate",
    "edit":     "flag-edit",
}

DECISION_EMOJI = {
    "APPROVED":  "✅",
    "REJECTED":  "❌",
    "ESCALATED": "📤",
    "DELETED":   "🗑️",
    "PENDING":   "⏳",
    "APPROVE":   "✅",
    "REJECT":    "❌",
    "ESCALATE":  "📤",
    "DELETE":    "🗑️",
}


def render_review_card(row, result, dup_map, tab_prefix="t"):
    rid     = str(row["ID"])
    title   = str(row.get("Review Title", "")).strip()
    text    = str(row.get("Review Detail Text", "")).strip()
    rating  = int(row.get("Rating", 3))
    seller  = str(row.get("Seller Name", "—"))
    sku     = str(row.get("SKU", "—"))
    nick    = str(row.get("Customer Nickname", "—"))
    created = str(row.get("Created Date", "—"))[:16]
    flags   = result["flags"]
    auto_action = result["auto_action"]
    decision = get_decision(rid)

    stars = "★" * rating + "☆" * (5 - rating)
    is_dup = rid in dup_map

    card_class = "auto-reject" if flags else "manual"

    with st.container():
        st.markdown(f'<div class="review-card {card_class}">', unsafe_allow_html=True)

        # Header row
        hcol1, hcol2 = st.columns([5, 2])
        with hcol1:
            st.markdown(f"**#{rid}** &nbsp; {stars} &nbsp; `{seller}` &nbsp; <span style='color:#6b7280;font-size:13px'>{created}</span>", unsafe_allow_html=True)
            st.markdown(f"**{title}**")
            st.markdown(f"<span style='color:#374151'>{text}</span>", unsafe_allow_html=True)
            st.caption(f"SKU: {sku}  ·  Customer: {nick}")

            # Flag tags
            if flags:
                tag_html = ""
                for label, sev in flags:
                    css = FLAG_STYLE.get(sev, "flag-edit")
                    tag_html += f'<span class="flag-tag {css}">{label}</span>'
                if is_dup:
                    tag_html += f'<span class="flag-tag flag-delete">Duplicate (same email+SKU)</span>'
                st.markdown(tag_html, unsafe_allow_html=True)
            elif is_dup:
                st.markdown('<span class="flag-tag flag-delete">Duplicate (same email+SKU)</span>', unsafe_allow_html=True)

        with hcol2:
            current = DECISION_EMOJI.get(decision, "⏳") + " " + decision
            st.markdown(f"**Decision:** {current}")

            # Action buttons
            bcol1, bcol2 = st.columns(2)
            if bcol1.button("✅ Approve", key=f"{tab_prefix}_approve_{rid}"):
                set_decision(rid, "APPROVED")
                st.rerun()
            if bcol2.button("❌ Reject", key=f"{tab_prefix}_reject_{rid}"):
                set_decision(rid, "REJECTED")
                st.rerun()

            bcol3, bcol4 = st.columns(2)
            if bcol3.button("📤 Escalate", key=f"{tab_prefix}_escalate_{rid}"):
                set_decision(rid, "ESCALATED")
                st.rerun()
            if bcol4.button("🗑️ Delete", key=f"{tab_prefix}_delete_{rid}"):
                set_decision(rid, "DELETED")
                st.rerun()

            note = st.text_input("Note", value=st.session_state.notes.get(rid, ""),
                                 key=f"{tab_prefix}_note_{rid}", placeholder="Optional note...")
            if note:
                st.session_state.notes[rid] = note

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("")  # spacing


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    main()
