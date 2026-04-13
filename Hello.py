"""
Product Category Predictor — powered by Groq + custom category map
"""

import os
import json
import openpyxl
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from collections import defaultdict
from groq import Groq

st.set_page_config(
    page_title="Product Category Predictor",
    page_icon="🏷️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-title {
        font-size: 2.4rem; font-weight: 700;
        background: linear-gradient(90deg, #f55036 0%, #ff8c00 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .subtitle { color: #888; font-size: 1rem; margin-bottom: 1.5rem; }
    .result-card {
        background: #f8f9fc; border-left: 4px solid #f55036;
        padding: 0.8rem 1rem; border-radius: 0 8px 8px 0; margin-bottom: 0.5rem;
    }
    .stTextArea textarea { border-radius: 10px !important; border: 2px solid #e0e0f0 !important; }
    .stTextArea textarea:focus { border-color: #f55036 !important; }
</style>
""", unsafe_allow_html=True)


# ─── Load & cache category map ────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_category_map(file_bytes: bytes):
    """
    Loads category_map.xlsx and builds lookup structures.
    Returns:
      - top_categories: list of top-level category names
      - top_to_l2: dict {top -> [l2, ...]}
      - l2_to_paths: dict {"top / l2" -> [full_path, ...]}
      - all_paths: list of all full paths
    """
    import io
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
    ws = wb.active

    all_paths = []
    top_to_l2 = defaultdict(set)
    l2_to_paths = defaultdict(list)

    for row in ws.iter_rows(min_row=2, values_only=True):
        path = row[2]  # "Category Path" column
        if not path:
            continue
        all_paths.append(path)
        parts = path.split(" / ")
        top = parts[0]
        if len(parts) >= 2:
            l2 = parts[1]
            top_to_l2[top].add(l2)
            l2_to_paths[f"{top} / {l2}"].append(path)

    top_categories = sorted(top_to_l2.keys())
    top_to_l2 = {k: sorted(v) for k, v in top_to_l2.items()}

    return top_categories, top_to_l2, dict(l2_to_paths), all_paths


# ─── 3-step Groq classification ───────────────────────────────────────────────

def groq_pick(client, model, system_prompt, user_msg, top_n):
    """Call Groq and return list of {category, score} dicts."""
    resp = client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_msg},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    return json.loads(raw).get("categories", [])


def predict(text: str, api_key: str, model: str, top_n: int,
            top_categories, top_to_l2, l2_to_paths) -> list[dict]:
    client = Groq(api_key=api_key)

    # ── Step 1: pick top-level category ──────────────────────────────────────
    top_list = "\n".join(f"- {c}" for c in top_categories)
    step1 = groq_pick(
        client, model,
        system_prompt=f"""You are a product categorization expert.
Given a product title, pick the single best matching top-level category from this list:
{top_list}

Respond with JSON only:
{{"categories": [{{"category": "<name>", "score": 0.95}}]}}
Return only 1 category. Score is a float 0-1.""",
        user_msg=f"Product: {text}",
        top_n=1,
    )

    if not step1:
        return []

    best_top = step1[0]["category"]
    # Fuzzy match in case Groq returns slightly different casing
    best_top = next((c for c in top_categories if c.lower() == best_top.lower()), best_top)

    if best_top not in top_to_l2:
        return [{"category": best_top, "score": step1[0]["score"]}]

    # ── Step 2: pick level-2 subcategory ─────────────────────────────────────
    l2_list = "\n".join(f"- {c}" for c in top_to_l2[best_top])
    step2 = groq_pick(
        client, model,
        system_prompt=f"""You are a product categorization expert.
The product belongs under the top-level category "{best_top}".
Pick the best matching subcategory from this list:
{l2_list}

Respond with JSON only:
{{"categories": [{{"category": "<name>", "score": 0.95}}]}}
Return only 1 category. Score is a float 0-1.""",
        user_msg=f"Product: {text}",
        top_n=1,
    )

    if not step2:
        return [{"category": best_top, "score": step1[0]["score"]}]

    best_l2 = step2[0]["category"]
    l2_key  = f"{best_top} / {best_l2}"
    # Fuzzy match
    l2_key = next(
        (k for k in l2_to_paths if k.lower() == l2_key.lower()),
        l2_key
    )

    if l2_key not in l2_to_paths:
        return [{"category": l2_key, "score": step2[0]["score"]}]

    # ── Step 3: pick the deepest matching full path ───────────────────────────
    candidates = l2_to_paths[l2_key]

    if len(candidates) == 1:
        return [{"category": candidates[0], "score": step2[0]["score"]}]

    # Send up to 80 candidates (fits in prompt easily)
    cand_list = "\n".join(f"- {c}" for c in candidates[:80])
    step3 = groq_pick(
        client, model,
        system_prompt=f"""You are a product categorization expert.
Pick the top {top_n} best matching full category paths for the product from this list:
{cand_list}

Respond with JSON only:
{{"categories": [
  {{"category": "<full path>", "score": 0.95}},
  ...
]}}
Return up to {top_n} categories ordered by confidence. Scores are floats 0-1.""",
        user_msg=f"Product: {text}",
        top_n=top_n,
    )

    return step3 if step3 else [{"category": l2_key, "score": step2[0]["score"]}]


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
            df["label"] = df["category"].apply(lambda x: x.split(" / ")[-1] if " / " in x else x)
            fig = go.Figure(go.Bar(
                x=df["score"] * 100, y=df["label"], orientation="h",
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
                height=max(300, len(preds) * 36),
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
    default_key = os.environ.get("GROQ_API_KEY", "")
    api_key = st.text_input("Paste your key here:", value=default_key,
                            type="password", placeholder="gsk_…")
    st.caption("Get a free key at [console.groq.com](https://console.groq.com)")

    st.markdown("---")
    st.markdown("## 📂 Category Map")
    cat_file = st.file_uploader("Upload category_map.xlsx", type=["xlsx"])
    if cat_file:
        st.success(f"✅ {cat_file.name} loaded")

    st.markdown("---")
    st.markdown("## ⚙️ Settings")
    model_choice    = st.selectbox("Model",
                                   ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
                                   help="70b most accurate. 8b fastest.")
    top_n           = st.slider("Top N categories", 1, 10, 5)
    score_threshold = st.slider("Min confidence", 0.0, 1.0, 0.0, 0.05)
    show_chart      = st.checkbox("Show confidence chart", value=True)
    show_hierarchy  = st.checkbox("Show category hierarchy", value=True)

    st.markdown("---")
    st.markdown("""### ℹ️ About
Uses a **3-step classification**:
1. Pick top-level category
2. Pick subcategory
3. Pick the deepest matching path

This keeps prompts small and accurate across 30K+ categories.

Free tier: 30 req/min on Groq.""")


# ─── Main ─────────────────────────────────────────────────────────────────────

st.markdown('<p class="main-title">🏷️ Product Category Predictor</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Classify products into your own category taxonomy — powered by Groq.</p>', unsafe_allow_html=True)

# ── Guards ─────────────────────────────────────────────────────────────────────
if not api_key:
    st.info("👈 Enter your Groq API key in the sidebar. Get one free at [console.groq.com](https://console.groq.com).")
    st.stop()

if not cat_file:
    st.info("👈 Upload your `category_map.xlsx` file in the sidebar to get started.")
    st.stop()

# ── Load categories ────────────────────────────────────────────────────────────
with st.spinner("Loading category map…"):
    file_bytes = cat_file.read()
    top_categories, top_to_l2, l2_to_paths, all_paths = load_category_map(file_bytes)

total_cats = len(all_paths)
st.success(f"✅ {total_cats:,} categories loaded across {len(top_categories)} top-level groups")

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_single, tab_batch, tab_explore = st.tabs(["🔍 Single Predict", "📦 Batch Predict", "🗂️ Explore Categories"])

EXAMPLES = [
    "Lykmera Famous TikTok Leggings, High Waist Yoga Pants for Women",
    "Apple AirPods Pro 2nd Generation Wireless Earbuds with USB-C Charging",
    "LEGO Star Wars The Skywalker Saga Deluxe Edition Nintendo Switch",
    "KitchenAid 5-Quart Artisan Stand Mixer with Dough Hook",
    "Harry Potter and the Sorcerer's Stone Hardcover Book",
    "Neutrogena Hydro Boost Hyaluronic Acid Face Moisturizer SPF 25",
]

# ── Single ─────────────────────────────────────────────────────────────────────
with tab_single:
    st.markdown("### Enter a product title or description")
    st.markdown("**Quick examples:**")
    cols = st.columns(3)
    for i, ex in enumerate(EXAMPLES):
        short = ex[:48] + "…" if len(ex) > 48 else ex
        if cols[i % 3].button(short, key=f"ex_{i}", use_container_width=True):
            st.session_state["product_text"] = ex

    product_text = st.text_area(
        "Product text",
        value=st.session_state.get("product_text", ""),
        height=100,
        placeholder="e.g. Nike Air Max 270 Men's Running Shoes…",
        label_visibility="collapsed",
    )

    if st.button("🔍 Predict Categories", type="primary", use_container_width=True):
        if product_text.strip():
            with st.spinner("Classifying (3-step)…"):
                try:
                    preds = predict(product_text, api_key, model_choice, top_n,
                                    top_categories, top_to_l2, l2_to_paths)
                    render_results(preds, score_threshold, show_chart, show_hierarchy)
                except Exception as e:
                    st.error(f"Prediction failed: {e}")
        else:
            st.warning("Please enter some product text first.")

# ── Batch ──────────────────────────────────────────────────────────────────────
with tab_batch:
    st.markdown("### Batch predict")
    top_n_batch = st.slider("Top N per product", 1, 5, 1, key="batch_topn")
    input_mode  = st.radio("Input method", ["📂 Upload file (CSV or Excel)", "📋 Paste a list"], horizontal=True)

    texts = []

    if input_mode == "📂 Upload file (CSV or Excel)":
        uploaded = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"])
        if uploaded:
            try:
                if uploaded.name.endswith((".xlsx", ".xls")):
                    df_input = pd.read_excel(uploaded)
                else:
                    try:
                        df_input = pd.read_csv(uploaded, encoding="utf-8")
                    except UnicodeDecodeError:
                        uploaded.seek(0)
                        df_input = pd.read_csv(uploaded, encoding="latin-1")
                st.dataframe(df_input.head(5), use_container_width=True)
                text_col = st.selectbox("Which column has product titles?", df_input.columns.tolist())
                texts = df_input[text_col].astype(str).dropna().tolist()
                st.caption(f"{len(texts):,} products ready.")
            except Exception as e:
                st.error(f"Could not read file: {e}")
        else:
            st.markdown("Supports `.csv`, `.xlsx`, `.xls`")

    else:
        pasted = st.text_area("Paste one product per line:", height=200,
                              placeholder="Nike Air Max 270\nKitchenAid Stand Mixer\nSony Headphones")
        if pasted.strip():
            texts = [t.strip() for t in pasted.strip().splitlines() if t.strip()]
            st.caption(f"{len(texts):,} products ready.")

    if texts:
        st.info(f"⚠️ Each product uses 3 Groq API calls. {len(texts)} products = {len(texts)*3} calls.")
        if st.button("🚀 Run Batch Prediction", type="primary"):
            prog = st.progress(0, text="Starting…")
            rows = []
            for i, text in enumerate(texts):
                prog.progress((i + 1) / len(texts),
                              text=f"Predicting {i+1} of {len(texts)}: {text[:60]}…")
                try:
                    preds = predict(text, api_key, model_choice, top_n_batch,
                                    top_categories, top_to_l2, l2_to_paths)
                    rows.append({
                        "input_text":   text,
                        "top_category": preds[0]["category"] if preds else "",
                        "top_score":    round(preds[0]["score"], 4) if preds else 0,
                        "top_3":        " | ".join(f"{p['category']} ({p['score']:.1%})" for p in preds[:3]),
                    })
                except Exception as e:
                    rows.append({"input_text": text, "top_category": f"ERROR: {e}",
                                 "top_score": 0, "top_3": ""})
            prog.progress(1.0, text=f"✅ Done — {len(rows):,} products predicted!")
            df_out = pd.DataFrame(rows)
            st.dataframe(df_out, use_container_width=True)
            st.download_button("⬇️ Download Results CSV",
                               df_out.to_csv(index=False).encode(),
                               "predictions.csv", "text/csv")
    else:
        if st.button("▶️ Try sample data"):
            sample = [
                "Sony WH-1000XM5 Wireless Noise Canceling Headphones",
                "Instant Pot Duo 7-in-1 Electric Pressure Cooker",
                "Hydro Flask Water Bottle 32 oz Wide Mouth",
                "Fitbit Charge 5 Advanced Fitness & Health Tracker",
            ]
            prog = st.progress(0, text="Starting…")
            rows = []
            for i, text in enumerate(sample):
                prog.progress((i + 1) / len(sample),
                              text=f"Predicting {i+1} of {len(sample)}: {text[:60]}…")
                try:
                    preds = predict(text, api_key, model_choice, 1,
                                    top_categories, top_to_l2, l2_to_paths)
                    rows.append({
                        "title": text,
                        "top_category": preds[0]["category"] if preds else "",
                        "score": f"{preds[0]['score']:.1%}" if preds else "",
                    })
                except Exception as e:
                    rows.append({"title": text, "top_category": f"ERROR: {e}", "score": ""})
            prog.progress(1.0, text="✅ Done!")
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

# ── Explore ────────────────────────────────────────────────────────────────────
with tab_explore:
    st.markdown("### 🗂️ Explore Your Category Map")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Categories", f"{len(all_paths):,}")
    c2.metric("Top-level Groups", len(top_categories))
    c3.metric("Max Depth", "9 levels")

    st.markdown("---")
    search = st.text_input("🔎 Search categories", placeholder="e.g. Electronics, Shoes, Kitchen…")

    if search:
        results = [p for p in all_paths if search.lower() in p.lower()]
        st.markdown(f"**{len(results):,} matches for '{search}':**")
        for p in results[:100]:
            st.markdown(f"- {p}")
        if len(results) > 100:
            st.caption(f"…and {len(results)-100} more. Refine your search.")
    else:
        st.markdown("**Top-level categories:**")
        cols = st.columns(3)
        for i, top in enumerate(top_categories):
            n_paths = sum(len(v) for k, v in l2_to_paths.items() if k.startswith(top))
            cols[i % 3].markdown(f"- **{top}** ({n_paths:,} paths)")
