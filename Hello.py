"""
Product Category Predictor
Strategy: TF-IDF shortlist (instant, free) + 1 Groq call to pick winner
Result: accurate, cheap (1 API call per product), fast
"""

import os, io, json, pickle
import numpy as np
import openpyxl
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from groq import Groq

st.set_page_config(page_title="Product Category Predictor", page_icon="🏷️",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .main-title {
        font-size:2.4rem; font-weight:700;
        background:linear-gradient(90deg,#f55036 0%,#ff8c00 100%);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        margin-bottom:0.2rem;
    }
    .subtitle { color:#888; font-size:1rem; margin-bottom:1.5rem; }
    .result-card {
        background:#f8f9fc; border-left:4px solid #f55036;
        padding:0.8rem 1rem; border-radius:0 8px 8px 0; margin-bottom:0.5rem;
    }
    .stTextArea textarea { border-radius:10px !important; border:2px solid #e0e0f0 !important; }
    .stTextArea textarea:focus { border-color:#f55036 !important; }
</style>
""", unsafe_allow_html=True)


# ─── Load & index category map ────────────────────────────────────────────────

def path_to_doc(path: str) -> str:
    """
    Convert a category path to a searchable document.
    Weights leaf parts more heavily so specific terms rank higher.
    e.g. 'Fashion / Men's Fashion / Clothing / Jeans / Skinny'
      -> all parts + last 3 parts repeated for boost
    """
    parts = path.split(" / ")
    return " ".join(parts) + " " + " ".join(parts[-3:]) * 2


@st.cache_resource(show_spinner=False)
def build_index(file_bytes: bytes):
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
    ws = wb.active

    all_paths = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[2]:
            all_paths.append(row[2])

    # Use only leaf nodes (most specific categories — no children)
    path_set = set(all_paths)
    leaves = [p for p in all_paths
              if not any(other.startswith(p + " / ") for other in path_set)]

    # Build TF-IDF index over leaf paths
    docs = [path_to_doc(p) for p in leaves]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
    matrix = vectorizer.fit_transform(docs)

    return leaves, vectorizer, matrix, all_paths


def shortlist(query: str, leaves, vectorizer, matrix, k: int = 30) -> list[str]:
    """Return top-k leaf paths by TF-IDF cosine similarity."""
    qvec = vectorizer.transform([query])
    sims = cosine_similarity(qvec, matrix)[0]
    top_idx = np.argsort(sims)[::-1][:k]
    return [leaves[i] for i in top_idx if sims[i] > 0]


# ─── Groq reranking ───────────────────────────────────────────────────────────

def groq_rerank(text: str, candidates: list[str], api_key: str,
                model: str, top_n: int) -> list[dict]:
    """
    Single Groq call: given product text + shortlisted candidates,
    pick the best top_n matches with confidence scores.
    """
    client = Groq(api_key=api_key)
    cand_list = "\n".join(f"- {c}" for c in candidates)

    resp = client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": f"""You are a product categorization expert.
Given a product title and a list of candidate category paths, pick the {top_n} best matching categories.
Consider the full meaning of the product — brand names, product type, gender, style, material.

Respond with JSON only:
{{
  "categories": [
    {{"category": "<full path>", "score": 0.95}},
    ...
  ]
}}

Rules:
- Return exactly {top_n} categories ordered by confidence descending
- Only pick from the provided candidate list — do not invent categories
- Scores are floats 0.0–1.0
- JSON only, nothing else"""
            },
            {
                "role": "user",
                "content": f"Product: {text}\n\nCandidates:\n{cand_list}"
            }
        ],
    )
    raw = resp.choices[0].message.content.strip()
    return json.loads(raw).get("categories", [])


def predict(text: str, api_key: str, model: str, top_n: int,
            leaves, vectorizer, matrix) -> list[dict]:
    # Step 1: TF-IDF shortlist (free, instant)
    candidates = shortlist(text, leaves, vectorizer, matrix, k=30)

    if not candidates:
        return []

    # Step 2: Groq picks the best from shortlist (1 API call)
    return groq_rerank(text, candidates, api_key, model, top_n)


# ─── Result renderer ──────────────────────────────────────────────────────────

def render_results(preds, score_threshold, show_chart, show_hierarchy):
    preds = [p for p in preds if p.get("score", 0) >= score_threshold]
    if not preds:
        st.warning("No categories above the confidence threshold.")
        return

    left, right = (st.columns([1, 1]) if show_chart else (st, None))

    with left:
        st.markdown("#### 🎯 Top Predictions")
        for i, p in enumerate(preds):
            pct   = p["score"] * 100
            color = "#f55036" if pct > 60 else "#ff8c00" if pct > 30 else "#ffd580"
            st.markdown(f"""
            <div class="result-card">
              <span style="font-size:.72rem;font-weight:700;color:#f55036;text-transform:uppercase;">#{i+1}</span>
              <div style="font-size:1rem;font-weight:600;color:#1a1a2e;">{p['category']}</div>
              <div style="display:flex;align-items:center;gap:8px;margin-top:4px;">
                <div style="flex:1;height:6px;background:#e8eaf6;border-radius:3px;">
                  <div style="width:{int(pct)}%;height:100%;background:{color};border-radius:3px;"></div>
                </div>
                <span style="font-size:.88rem;color:#555;">{pct:.1f}%</span>
              </div>
            </div>""", unsafe_allow_html=True)

    if show_chart and right:
        with right:
            st.markdown("#### 📊 Confidence Chart")
            df = pd.DataFrame(preds).sort_values("score")
            df["label"] = df["category"].apply(
                lambda x: " / ".join(x.split(" / ")[-2:]) if " / " in x else x)
            fig = go.Figure(go.Bar(
                x=df["score"]*100, y=df["label"], orientation="h",
                marker=dict(color=df["score"]*100,
                            colorscale=[[0,"#ffd580"],[0.5,"#ff8c00"],[1,"#f55036"]],
                            showscale=False),
                text=[f"{s*100:.1f}%" for s in df["score"]],
                textposition="outside",
                hovertext=df["category"], hoverinfo="text+x",
            ))
            fig.update_layout(
                xaxis_title="Confidence (%)",
                margin=dict(l=0, r=60, t=10, b=30),
                height=max(300, len(preds)*36),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(range=[0, 115]),
            )
            st.plotly_chart(fig, use_container_width=True)

    if show_hierarchy:
        lines, seen = [], set()
        for p in preds:
            parts = [x.strip() for x in p["category"].split(" / ") if x.strip()]
            if len(parts) > 1:
                if parts[0] not in seen:
                    lines.append(f"📁 **{parts[0]}**")
                    seen.add(parts[0])
                for d, part in enumerate(parts[1:], 1):
                    lines.append(f"{'  '*d}└─ {part}")
            else:
                lines.append(f"🏷️ {p['category']}")
        if lines:
            st.markdown("#### 🌲 Category Hierarchy")
            st.markdown("\n".join(lines))


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔑 Groq API Key")
    api_key = st.text_input("Paste your key here:",
                            value=os.environ.get("GROQ_API_KEY", ""),
                            type="password", placeholder="gsk_…")
    st.caption("Free key at [console.groq.com](https://console.groq.com)")

    st.markdown("---")
    st.markdown("## 📂 Category Map")
    cat_file = st.file_uploader("Upload category_map.xlsx", type=["xlsx"])
    if cat_file:
        st.success(f"✅ {cat_file.name} loaded")

    st.markdown("---")
    st.markdown("## ⚙️ Settings")
    model_choice    = st.selectbox("Groq model",
                                   ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
                                   help="70b most accurate. 8b fastest & cheapest.")
    top_n           = st.slider("Top N results", 1, 10, 5)
    shortlist_k     = st.slider("Shortlist size (TF-IDF candidates)", 10, 50, 30,
                                help="More = higher recall but larger prompt. 30 is a good balance.")
    score_threshold = st.slider("Min confidence", 0.0, 1.0, 0.0, 0.05)
    show_chart      = st.checkbox("Show confidence chart", value=True)
    show_hierarchy  = st.checkbox("Show category hierarchy", value=True)

    st.markdown("---")
    st.markdown("""### ℹ️ How it works
**Step 1 — TF-IDF shortlist** (free, <10ms)
Finds 30 candidate leaf categories by keyword similarity.

**Step 2 — Groq reranks** (1 API call)
Picks the best matches from candidates using semantic understanding.

**Result:** 1 call per product instead of 3.
Accurate on both keywords *and* brand/context.""")


# ─── Main ─────────────────────────────────────────────────────────────────────

st.markdown('<p class="main-title">🏷️ Product Category Predictor</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">TF-IDF shortlisting + Groq reranking — 1 API call per product, deep category paths.</p>', unsafe_allow_html=True)

if not api_key:
    st.info("👈 Enter your Groq API key in the sidebar.")
    st.stop()

if not cat_file:
    st.info("👈 Upload your `category_map.xlsx` in the sidebar.")
    st.stop()

# Build index
with st.spinner("Building category index (one-time, ~2s)…"):
    file_bytes = cat_file.read()
    leaves, vectorizer, matrix, all_paths = build_index(file_bytes)

st.success(f"✅ Index ready — {len(leaves):,} leaf categories indexed")

# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab_single, tab_batch, tab_explore = st.tabs(["🔍 Single Predict", "📦 Batch Predict", "🗂️ Explore"])

EXAMPLES = [
    "Baggy Unit Denim Jeans Men's Streetwear",
    "Apple AirPods Pro 2nd Generation Wireless Earbuds",
    "LEGO Star Wars The Skywalker Saga Nintendo Switch",
    "KitchenAid 5-Quart Artisan Stand Mixer",
    "Harry Potter and the Sorcerer's Stone Hardcover",
    "Neutrogena Hydro Boost Face Moisturizer SPF 25",
]

# ── Single ─────────────────────────────────────────────────────────────────────
with tab_single:
    st.markdown("### Enter a product title or description")
    st.markdown("**Quick examples:**")
    cols = st.columns(3)
    for i, ex in enumerate(EXAMPLES):
        short = ex[:46] + "…" if len(ex) > 46 else ex
        if cols[i % 3].button(short, key=f"ex_{i}", use_container_width=True):
            st.session_state["product_text"] = ex

    col_title, col_brand = st.columns([3, 1])
    with col_title:
        product_text = st.text_area(
            "Product title",
            value=st.session_state.get("product_text", ""),
            height=90,
            placeholder="e.g. Air Max 270 Men's Running Shoes…",
        )
    with col_brand:
        brand = st.text_input(
            "Brand *(optional)*",
            placeholder="e.g. Nike",
            help="Adding a brand helps Groq disambiguate — e.g. Apple → Electronics not Grocery.",
        )

    if st.button("🔍 Predict Categories", type="primary", use_container_width=True):
        if product_text.strip():
            query = f"{brand.strip()} {product_text.strip()}".strip() if brand.strip() else product_text.strip()
            col_status = st.empty()
            with col_status:
                with st.spinner("Step 1: TF-IDF shortlisting…"):
                    candidates = shortlist(query, leaves, vectorizer, matrix, shortlist_k)
                with st.spinner(f"Step 2: Groq reranking {len(candidates)} candidates…"):
                    try:
                        preds = groq_rerank(query, candidates, api_key, model_choice, top_n)
                        col_status.empty()
                        render_results(preds, score_threshold, show_chart, show_hierarchy)
                        with st.expander(f"🔎 TF-IDF shortlist ({len(candidates)} candidates sent to Groq)"):
                            for c in candidates:
                                st.markdown(f"- {c}")
                    except Exception as e:
                        st.error(f"Groq error: {e}")
        else:
            st.warning("Please enter some product text first.")

# ── Batch ──────────────────────────────────────────────────────────────────────
with tab_batch:
    st.markdown("### Batch predict")
    top_n_batch = st.slider("Top N per product", 1, 5, 1, key="batch_topn")
    input_mode  = st.radio("Input method",
                           ["📂 Upload file (CSV or Excel)", "📋 Paste a list"],
                           horizontal=True)
    texts = []
    brands = []

    if input_mode == "📂 Upload file (CSV or Excel)":
        uploaded = st.file_uploader("Upload CSV or Excel", type=["csv","xlsx","xls"])
        if uploaded:
            try:
                if uploaded.name.endswith((".xlsx",".xls")):
                    df_input = pd.read_excel(uploaded)
                else:
                    try:
                        df_input = pd.read_csv(uploaded, encoding="utf-8")
                    except UnicodeDecodeError:
                        uploaded.seek(0)
                        df_input = pd.read_csv(uploaded, encoding="latin-1")
                st.dataframe(df_input.head(5), use_container_width=True)
                col_tc, col_bc = st.columns([2, 1])
                with col_tc:
                    text_col = st.selectbox("Product title column", df_input.columns.tolist())
                with col_bc:
                    brand_col = st.selectbox("Brand column *(optional)*",
                                            ["— none —"] + df_input.columns.tolist())
                has_brand_col = brand_col != "— none —"
                texts  = df_input[text_col].astype(str).fillna("").tolist()
                brands = df_input[brand_col].astype(str).fillna("").tolist() if has_brand_col else [""] * len(texts)
                st.caption(f"{len(texts):,} products ready — {len(texts)} Groq calls total.")
            except Exception as e:
                st.error(f"Could not read file: {e}")
    else:
        pasted = st.text_area("Paste one product per line:", height=180,
                              placeholder="Nike Air Max 270\nKitchenAid Stand Mixer")
        brand_prefix = st.text_input("Brand *(optional — applies to all pasted products)*",
                                    placeholder="e.g. Nike", key="paste_brand")
        if pasted.strip():
            texts  = [t.strip() for t in pasted.strip().splitlines() if t.strip()]
            brands = [brand_prefix.strip() if brand_prefix else ""] * len(texts)
            st.caption(f"{len(texts):,} products ready — {len(texts)} Groq calls total.")

    if texts:
        if st.button("🚀 Run Batch Prediction", type="primary"):
            prog = st.progress(0, text="Starting…")
            rows = []
            for i, text in enumerate(texts):
                b = brands[i] if i < len(brands) else ""
                query = f"{b.strip()} {text.strip()}".strip() if b.strip() else text.strip()
                prog.progress((i+1)/len(texts),
                              text=f"Predicting {i+1}/{len(texts)}: {text[:55]}…")
                try:
                    cands = shortlist(query, leaves, vectorizer, matrix, shortlist_k)
                    preds = groq_rerank(query, cands, api_key, model_choice, top_n_batch)
                    rows.append({
                        "input_text":   text,
                        "brand":        b,
                        "top_category": preds[0]["category"] if preds else "",
                        "top_score":    round(preds[0]["score"], 4) if preds else 0,
                        "top_3":        " | ".join(f"{p['category']} ({p['score']:.1%})"
                                                   for p in preds[:3]),
                    })
                except Exception as e:
                    rows.append({"input_text": text, "brand": b,
                                 "top_category": f"ERROR: {e}", "top_score": 0, "top_3": ""})
            prog.progress(1.0, text=f"✅ Done — {len(rows):,} products predicted!")
            df_out = pd.DataFrame(rows)
            st.dataframe(df_out, use_container_width=True)
            st.download_button("⬇️ Download Results CSV",
                               df_out.to_csv(index=False).encode(),
                               "predictions.csv", "text/csv")
    else:
        if st.button("▶️ Try sample data"):
            sample = ["Sony WH-1000XM5 Wireless Headphones",
                      "Instant Pot Duo 7-in-1 Pressure Cooker",
                      "Baggy Unit Denim Jeans Men",
                      "Harry Potter Hardcover Book"]
            prog = st.progress(0, text="Starting…")
            rows = []
            for i, text in enumerate(sample):
                prog.progress((i+1)/len(sample), text=f"Predicting {i+1}/{len(sample)}…")
                try:
                    cands = shortlist(text, leaves, vectorizer, matrix, shortlist_k)
                    preds = groq_rerank(text, cands, api_key, model_choice, 1)
                    rows.append({"title": text,
                                 "predicted_category": preds[0]["category"] if preds else "",
                                 "confidence": f"{preds[0]['score']:.1%}" if preds else ""})
                except Exception as e:
                    rows.append({"title": text, "predicted_category": f"ERROR: {e}", "confidence": ""})
            prog.progress(1.0, text="✅ Done!")
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

# ── Explore ────────────────────────────────────────────────────────────────────
with tab_explore:
    st.markdown("### 🗂️ Explore Category Map")
    tops = sorted(set(p.split(" / ")[0] for p in all_paths))
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Paths", f"{len(all_paths):,}")
    c2.metric("Leaf Categories", f"{len(leaves):,}")
    c3.metric("Top-level Groups", len(tops))

    st.markdown("---")
    search = st.text_input("🔎 Search", placeholder="e.g. Jeans, Headphones, Mixer…")
    if search:
        results = [p for p in all_paths if search.lower() in p.lower()]
        st.markdown(f"**{len(results):,} matches:**")
        for p in results[:100]:
            depth = len(p.split(" / ")) - 1
            indent = "  " * depth
            st.markdown(f"{indent}{'└─ ' if depth else ''}{p.split(' / ')[-1]}  \n`{p}`")
        if len(results) > 100:
            st.caption(f"…and {len(results)-100} more.")
    else:
        st.markdown("**Top-level categories:**")
        cols = st.columns(3)
        for i, top in enumerate(tops):
            count = sum(1 for p in leaves if p.startswith(top))
            cols[i % 3].markdown(f"- **{top}** ({count:,} leaves)")
