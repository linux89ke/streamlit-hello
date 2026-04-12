"""
Product Category Predictor — powered by Google Gemini
"""

import os
import json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import google.generativeai as genai

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
        background: linear-gradient(90deg, #4285f4 0%, #0f9d58 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .subtitle { color: #888; font-size: 1rem; margin-bottom: 1.5rem; }
    .result-card {
        background: #f8f9fc; border-left: 4px solid #4285f4;
        padding: 0.8rem 1rem; border-radius: 0 8px 8px 0; margin-bottom: 0.5rem;
    }
    .stTextArea textarea { border-radius: 10px !important; border: 2px solid #e0e0f0 !important; }
    .stTextArea textarea:focus { border-color: #4285f4 !important; }
    .api-box { background: #f0f4ff; border: 1px solid #c7d7ff; border-radius: 12px; padding: 1.2rem; margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

SYSTEM_PROMPT = """You are a product categorization expert trained on Amazon's product catalog.
Given a product title or description, return the top predicted categories with confidence scores.
You MUST respond with valid JSON only — no markdown, no explanation, just the JSON object.
Format:
{
  "categories": [
    {"category": "Sports & Outdoors > Exercise & Fitness > Yoga > Leggings", "score": 0.97},
    {"category": "Clothing, Shoes & Jewelry > Women > Clothing > Activewear", "score": 0.91}
  ]
}
Rules:
- Return exactly TOP_N categories, ordered by confidence descending
- Use Amazon-style hierarchical category paths with " > " as separator
- Scores are floats between 0.0 and 1.0
- Be specific — go 3-4 levels deep where possible
- JSON only, nothing else"""


def predict_gemini(text, api_key, top_n, model_name):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=SYSTEM_PROMPT.replace("TOP_N", str(top_n)),
    )
    response = model.generate_content(
        f"Product: {text}",
        generation_config=genai.GenerationConfig(temperature=0.1, response_mime_type="application/json"),
    )
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip()).get("categories", [])


def render_results(preds, score_threshold, show_chart, show_hierarchy):
    preds = [p for p in preds if p.get("score", 0) >= score_threshold]
    if not preds:
        st.warning("No categories above the confidence threshold.")
        return

    left, right = (st.columns([1, 1]) if show_chart else (st, None))

    with left:
        st.markdown("#### 🎯 Top Predictions")
        for i, p in enumerate(preds):
            pct = p["score"] * 100
            color = "#4285f4" if pct > 60 else "#34a853" if pct > 30 else "#a8d5b5"
            st.markdown(f"""
            <div class="result-card">
              <span style="font-size:.72rem;font-weight:700;color:#4285f4;text-transform:uppercase;">#{i+1}</span>
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
            df["label"] = df["category"].apply(lambda x: x.split(" > ")[-1] if " > " in x else x)
            fig = go.Figure(go.Bar(
                x=df["score"] * 100, y=df["label"], orientation="h",
                marker=dict(color=df["score"]*100,
                            colorscale=[[0,"#a8d5b5"],[0.5,"#34a853"],[1,"#4285f4"]],
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
            parts = [x.strip() for x in p["category"].split(" > ") if x.strip()]
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
    st.markdown("## 🔑 Gemini API Key")
    default_key = os.environ.get("GEMINI_API_KEY", "")
    api_key = st.text_input(
        "Paste your key here:",
        value=default_key,
        type="password",
        placeholder="AIza…",
    )
    st.caption("Get a free key at [aistudio.google.com](https://aistudio.google.com/app/apikey)")

    st.markdown("---")
    st.markdown("## ⚙️ Settings")
    model_choice    = st.selectbox("Gemini model",
                                   ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
                                   help="2.0 Flash is fastest. Pro is most accurate.")
    top_n           = st.slider("Top N categories", 3, 20, 10)
    score_threshold = st.slider("Min confidence", 0.0, 1.0, 0.0, 0.05)
    show_chart      = st.checkbox("Show confidence chart", value=True)
    show_hierarchy  = st.checkbox("Show category hierarchy", value=True)

    st.markdown("---")
    st.markdown("""### ℹ️ About
Powered by **Google Gemini** — no model download, instant startup.

Categories follow Amazon's taxonomy with 3-4 level hierarchy.

Free tier: 15 req/min on Flash models.""")


# ─── Main ─────────────────────────────────────────────────────────────────────

st.markdown('<p class="main-title">🏷️ Product Category Predictor</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Predict Amazon-style product categories instantly — powered by Google Gemini, no model download needed.</p>', unsafe_allow_html=True)

if not api_key:
    st.info("👈 Enter your Gemini API key in the sidebar to get started. Get one free at [aistudio.google.com](https://aistudio.google.com/app/apikey).")
    st.stop()

tab_single, tab_batch = st.tabs(["🔍 Single Predict", "📦 Batch Predict"])

EXAMPLES = [
    "Lykmera Famous TikTok Leggings, High Waist Yoga Pants for Women, Booty Bubble Butt Lifting Workout Running Tights",
    "Apple AirPods Pro 2nd Generation Wireless Earbuds with USB-C Charging",
    "LEGO Star Wars The Skywalker Saga Deluxe Edition Nintendo Switch",
    "KitchenAid 5-Quart Artisan Stand Mixer with Dough Hook Flat Beater and Wire Whip",
    "Harry Potter and the Sorcerer's Stone Hardcover Book by J.K. Rowling",
    "Neutrogena Hydro Boost Hyaluronic Acid Hydrating Daily Face Moisturizer SPF 25",
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
            with st.spinner("Asking Gemini…"):
                try:
                    preds = predict_gemini(product_text, api_key, top_n, model_choice)
                    render_results(preds, score_threshold, show_chart, show_hierarchy)
                except Exception as e:
                    st.error(f"Prediction failed: {e}")
        else:
            st.warning("Please enter some product text first.")

# ── Batch ──────────────────────────────────────────────────────────────────────
with tab_batch:
    st.markdown("### Batch predict from a CSV file")
    uploaded = st.file_uploader("Upload CSV", type=["csv"])

    if uploaded:
        df_input = pd.read_csv(uploaded)
        st.dataframe(df_input.head(5), use_container_width=True)
        text_col    = st.selectbox("Text column", df_input.columns.tolist())
        top_n_batch = st.slider("Top N per product", 1, 5, 3, key="batch_topn")

        if st.button("🚀 Run Batch Prediction", type="primary"):
            texts = df_input[text_col].astype(str).tolist()
            prog  = st.progress(0, text="Starting…")
            rows  = []
            for i, text in enumerate(texts):
                prog.progress((i) / len(texts), text=f"Row {i+1} of {len(texts)}…")
                try:
                    preds = predict_gemini(text, api_key, top_n_batch, model_choice)
                    rows.append({
                        "input_text":   text,
                        "top_category": preds[0]["category"] if preds else "",
                        "top_score":    round(preds[0]["score"], 4) if preds else 0,
                        "top_3":        " | ".join(f"{p['category']} ({p['score']:.1%})" for p in preds[:3]),
                    })
                except Exception as e:
                    rows.append({"input_text": text, "top_category": f"ERROR: {e}", "top_score": 0, "top_3": ""})
            prog.progress(1.0, text="Done!")
            df_out = pd.DataFrame(rows)
            st.success(f"✅ Predicted {len(df_out):,} products.")
            st.dataframe(df_out, use_container_width=True)
            st.download_button("⬇️ Download CSV", df_out.to_csv(index=False).encode(), "predictions.csv", "text/csv")
    else:
        st.markdown("""
        **Expected CSV format:**
        ```
        title
        Nike Air Max 270 Men's Running Shoes
        KitchenAid Stand Mixer 5qt
        ```
        """)
        if st.button("▶️ Try sample data"):
            sample = [
                "Sony WH-1000XM5 Wireless Noise Canceling Headphones",
                "Instant Pot Duo 7-in-1 Electric Pressure Cooker 6 Qt",
                "Hydro Flask Water Bottle 32 oz Wide Mouth",
                "The Great Gatsby Paperback – F. Scott Fitzgerald",
                "Fitbit Charge 5 Advanced Fitness & Health Tracker",
            ]
            with st.spinner("Asking Gemini…"):
                try:
                    rows = []
                    for text in sample:
                        preds = predict_gemini(text, api_key, 3, model_choice)
                        rows.append({
                            "title": text,
                            "top_category": preds[0]["category"] if preds else "",
                            "predictions": " | ".join(f"{p['category']} ({p['score']:.1%})" for p in preds[:3]),
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)
                except Exception as e:
                    st.error(f"Failed: {e}")
