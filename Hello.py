"""
Product Category Predictor — Streamlit App
Uses the pretrained DistilBERT model from yang-zhang/product_category
trained on Amazon product data (~1900 categories).
"""

import os
import json
import urllib.request
from pathlib import Path

import streamlit as st
import torch
import torch.nn as nn
import pandas as pd
import plotly.graph_objects as go
from transformers import DistilBertTokenizer, DistilBertModel

# ─── Config ───────────────────────────────────────────────────────────────────

MODEL_URL = "https://github.com/yang-zhang/product_category/releases/download/v0.0.1/transformer_20210307D3.ckpt"
MODEL_PATH = Path("data/transformer_20210307D3.ckpt")
I2CAT_PATH = Path("data/i2cat.json")
TOKENIZER_NAME = "distilbert-base-cased"
MAX_SEQ_LENGTH = 128
TOP_N_DEFAULT = 10

# ─── Page setup ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Product Category Predictor",
    page_icon="🏷️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main-title {
        font-size: 2.4rem;
        font-weight: 700;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .subtitle {
        color: #888;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .result-card {
        background: #f8f9fc;
        border-left: 4px solid #667eea;
        padding: 1rem 1.2rem;
        border-radius: 0 8px 8px 0;
        margin-bottom: 0.6rem;
    }
    .category-rank {
        font-size: 0.75rem;
        font-weight: 700;
        color: #667eea;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .category-name {
        font-size: 1.05rem;
        font-weight: 600;
        color: #1a1a2e;
    }
    .category-score {
        font-size: 0.9rem;
        color: #555;
    }
    .example-btn button {
        background: transparent !important;
        border: 1px solid #667eea !important;
        color: #667eea !important;
        border-radius: 20px !important;
        padding: 0.2rem 0.8rem !important;
        font-size: 0.82rem !important;
    }
    .stTextArea textarea {
        border-radius: 10px !important;
        border: 2px solid #e0e0f0 !important;
        font-size: 1rem !important;
    }
    .stTextArea textarea:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 2px rgba(102,126,234,0.2) !important;
    }
    .upload-section {
        background: #f0f2ff;
        border-radius: 12px;
        padding: 1.2rem;
        margin-top: 1rem;
    }
    .stProgress .st-bo { background: #667eea; }
    div[data-testid="metric-container"] {
        background: #f8f9fc;
        border: 1px solid #e8eaf6;
        border-radius: 10px;
        padding: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)

# ─── Model definition (must match training architecture) ──────────────────────

class ProductCategoryModel(nn.Module):
    def __init__(self, num_labels: int, model_name: str = TOKENIZER_NAME):
        super().__init__()
        self.bert = DistilBertModel.from_pretrained(model_name)
        self.classifier = nn.Linear(self.bert.config.hidden_size, num_labels)

    def forward(self, input_ids, attention_mask):
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        cls = outputs.last_hidden_state[:, 0, :]
        return self.classifier(cls)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def download_model():
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MODEL_PATH.exists():
        with st.spinner("⬇️  Downloading pretrained model (first run only) …"):
            progress = st.progress(0)

            def reporthook(count, block_size, total_size):
                if total_size > 0:
                    progress.progress(min(int(count * block_size / total_size * 100), 100))

            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH, reporthook)
            progress.empty()
        st.success("Model downloaded!")


def extract_i2cat_from_checkpoint(ckpt_path: Path) -> list[str]:
    """Pull the i2cat list out of the Lightning checkpoint hyper_parameters."""
    ckpt = torch.load(ckpt_path, map_location="cpu")
    hp = ckpt.get("hyper_parameters", {})
    # Try common keys
    for key in ("i2cat", "idx_to_cat", "categories", "label_names"):
        if key in hp:
            return hp[key]
    # Fallback: infer from classifier weight shape
    state = ckpt.get("state_dict", {})
    for k, v in state.items():
        if "classifier" in k and v.ndim == 2:
            n = v.shape[0]
            return [f"Category_{i}" for i in range(n)]
    raise ValueError("Could not find category list in checkpoint.")


@st.cache_resource(show_spinner=False)
def load_model_and_tokenizer():
    download_model()

    with st.spinner("🔧  Loading model …"):
        ckpt = torch.load(MODEL_PATH, map_location="cpu")
        state_dict = ckpt["state_dict"]

        # Determine num_labels from classifier weight
        cls_weight_key = next(k for k in state_dict if "classifier" in k and "weight" in k)
        num_labels = state_dict[cls_weight_key].shape[0]

        # Remap Lightning keys → plain PyTorch keys
        new_state = {}
        for k, v in state_dict.items():
            # Lightning wraps model as self.model or direct attribute
            new_key = k
            for prefix in ("model.", "bert_model.", "transformer."):
                if k.startswith(prefix):
                    new_key = k[len(prefix):]
                    break
            new_state[new_key] = v

        model = ProductCategoryModel(num_labels=num_labels)
        missing, unexpected = model.load_state_dict(new_state, strict=False)
        model.eval()

        # Load / build i2cat
        if I2CAT_PATH.exists():
            with open(I2CAT_PATH) as f:
                i2cat = json.load(f)
        else:
            try:
                i2cat = extract_i2cat_from_checkpoint(MODEL_PATH)
                I2CAT_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(I2CAT_PATH, "w") as f:
                    json.dump(i2cat, f)
            except Exception:
                i2cat = [f"Category_{i}" for i in range(num_labels)]

        tokenizer = DistilBertTokenizer.from_pretrained(TOKENIZER_NAME)

    return model, tokenizer, i2cat


def predict(text: str, model, tokenizer, i2cat, top_n: int = TOP_N_DEFAULT):
    encoding = tokenizer(
        text,
        max_length=MAX_SEQ_LENGTH,
        padding="max_length",
        truncation=True,
        return_tensors="pt",
    )
    with torch.no_grad():
        logits = model(encoding["input_ids"], encoding["attention_mask"])
        probs = torch.sigmoid(logits).squeeze().numpy()

    results = sorted(
        [{"category": i2cat[i], "score": float(probs[i])} for i in range(len(i2cat))],
        key=lambda x: x["score"],
        reverse=True,
    )
    return results[:top_n]


def batch_predict(texts: list[str], model, tokenizer, i2cat, top_n: int = 5):
    results = []
    for text in texts:
        preds = predict(text, model, tokenizer, i2cat, top_n)
        results.append({
            "title": text,
            "top_category": preds[0]["category"] if preds else "",
            "top_score": round(preds[0]["score"], 4) if preds else 0,
            "predictions": " | ".join(f"{p['category']} ({p['score']:.2%})" for p in preds[:3]),
        })
    return pd.DataFrame(results)


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️  Settings")
    top_n = st.slider("Top N categories", min_value=3, max_value=20, value=10)
    score_threshold = st.slider("Confidence threshold", 0.0, 1.0, 0.0, 0.05,
                                help="Hide predictions below this score")
    show_chart = st.checkbox("Show confidence chart", value=True)
    show_hierarchy = st.checkbox("Show category hierarchy", value=True)

    st.markdown("---")
    st.markdown("### ℹ️  About")
    st.markdown("""
    Pretrained on **500K Amazon products** across **~1,900 categories** using:
    - `distilbert-base-cased`
    - Multi-label classification
    - [Source repo](https://github.com/yang-zhang/product_category)

    > *For research purposes only.*
    """)

# ─── Main UI ──────────────────────────────────────────────────────────────────

st.markdown('<p class="main-title">🏷️ Product Category Predictor</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Predict Amazon-style product categories from titles or descriptions using a pretrained DistilBERT model.</p>', unsafe_allow_html=True)

# Load model
try:
    model, tokenizer, i2cat = load_model_and_tokenizer()
    st.success(f"✅  Model ready — {len(i2cat):,} categories loaded", icon="✅")
except Exception as e:
    st.error(f"Failed to load model: {e}")
    st.stop()

# Tabs
tab_single, tab_batch, tab_explore = st.tabs(["🔍 Single Predict", "📦 Batch Predict", "🗂️ Explore Categories"])

# ── Tab 1: Single prediction ──────────────────────────────────────────────────
with tab_single:
    st.markdown("### Enter a product title or description")

    EXAMPLES = [
        "Lykmera Famous TikTok Leggings, High Waist Yoga Pants for Women, Booty Bubble Butt Lifting Workout Running Tights",
        "Apple AirPods Pro (2nd Generation) Wireless Earbuds with USB-C Charging",
        "LEGO Star Wars: The Skywalker Saga Deluxe Edition - Nintendo Switch",
        "KitchenAid 5-Quart Artisan Stand Mixer with Dough Hook, Flat Beater and Wire Whip",
        "Harry Potter and the Sorcerer's Stone Hardcover Book",
        "Neutrogena Hydro Boost Hyaluronic Acid Hydrating Daily Face Moisturizer",
    ]

    st.markdown("**Quick examples:**")
    cols = st.columns(3)
    for i, ex in enumerate(EXAMPLES):
        short = ex[:45] + "…" if len(ex) > 45 else ex
        if cols[i % 3].button(short, key=f"ex_{i}", use_container_width=True):
            st.session_state["product_text"] = ex

    product_text = st.text_area(
        "Product text",
        value=st.session_state.get("product_text", ""),
        height=100,
        placeholder="e.g. Nike Air Max 270 Men's Running Shoes …",
        label_visibility="collapsed",
    )

    predict_btn = st.button("🔍  Predict Categories", type="primary", use_container_width=True)

    if predict_btn and product_text.strip():
        with st.spinner("Predicting …"):
            preds = predict(product_text, model, tokenizer, i2cat, top_n)

        preds = [p for p in preds if p["score"] >= score_threshold]

        if not preds:
            st.warning("No categories above the confidence threshold.")
        else:
            col_results, col_chart = st.columns([1, 1]) if show_chart else (st, None)

            with col_results:
                st.markdown("#### 🎯 Top Predictions")
                for i, p in enumerate(preds):
                    pct = p["score"] * 100
                    bar_width = int(pct)
                    color = "#667eea" if pct > 60 else "#a78bfa" if pct > 30 else "#c4b5fd"
                    st.markdown(f"""
                    <div class="result-card">
                      <span class="category-rank">#{i+1}</span>
                      <div class="category-name">{p['category']}</div>
                      <div style="display:flex;align-items:center;gap:8px;margin-top:4px;">
                        <div style="flex:1;height:6px;background:#e8eaf6;border-radius:3px;">
                          <div style="width:{bar_width}%;height:100%;background:{color};border-radius:3px;"></div>
                        </div>
                        <span class="category-score">{pct:.1f}%</span>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

            if show_chart and col_chart:
                with col_chart:
                    st.markdown("#### 📊 Confidence Chart")
                    df = pd.DataFrame(preds).sort_values("score")
                    fig = go.Figure(go.Bar(
                        x=df["score"] * 100,
                        y=df["category"],
                        orientation="h",
                        marker=dict(
                            color=df["score"] * 100,
                            colorscale=[[0, "#c4b5fd"], [0.5, "#a78bfa"], [1, "#667eea"]],
                            showscale=False,
                        ),
                        text=[f"{s*100:.1f}%" for s in df["score"]],
                        textposition="outside",
                    ))
                    fig.update_layout(
                        xaxis_title="Confidence (%)",
                        margin=dict(l=0, r=60, t=10, b=30),
                        height=max(300, len(preds) * 36),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(size=12),
                        xaxis=dict(range=[0, 110]),
                    )
                    st.plotly_chart(fig, use_container_width=True)

            if show_hierarchy:
                st.markdown("#### 🌲 Category Hierarchy")
                seen_roots = set()
                tree_lines = []
                for p in preds:
                    parts = p["category"].split("|") if "|" in p["category"] else p["category"].split(" > ")
                    parts = [x.strip() for x in parts if x.strip()]
                    if len(parts) > 1:
                        root = parts[0]
                        if root not in seen_roots:
                            tree_lines.append(f"📁 **{root}**")
                            seen_roots.add(root)
                        for depth, part in enumerate(parts[1:], 1):
                            tree_lines.append(f"{'  ' * depth}└─ {part}")
                    else:
                        tree_lines.append(f"🏷️ {p['category']}")
                if tree_lines:
                    st.markdown("\n".join(tree_lines))

    elif predict_btn:
        st.warning("Please enter some product text first.")

# ── Tab 2: Batch prediction ───────────────────────────────────────────────────
with tab_batch:
    st.markdown("### Batch predict from a CSV file")
    st.markdown("Upload a CSV with a **`title`** column (or any text column) to predict categories in bulk.")

    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

    if uploaded_file:
        df_input = pd.read_csv(uploaded_file)
        st.markdown(f"**{len(df_input):,} rows loaded.** Preview:")
        st.dataframe(df_input.head(5), use_container_width=True)

        text_col = st.selectbox("Select the text column", df_input.columns.tolist())
        top_n_batch = st.slider("Top N per product", 1, 10, 3, key="batch_topn")

        if st.button("🚀  Run Batch Prediction", type="primary"):
            texts = df_input[text_col].astype(str).tolist()
            progress_bar = st.progress(0)
            results = []
            for i, text in enumerate(texts):
                preds = predict(text, model, tokenizer, i2cat, top_n_batch)
                results.append({
                    "input_text": text,
                    "top_category": preds[0]["category"] if preds else "",
                    "top_score": round(preds[0]["score"], 4) if preds else 0,
                    "top_3_predictions": " | ".join(
                        f"{p['category']} ({p['score']:.2%})" for p in preds[:3]
                    ),
                })
                progress_bar.progress((i + 1) / len(texts))

            progress_bar.empty()
            df_out = pd.DataFrame(results)
            st.success(f"Done! Predicted {len(df_out):,} products.")
            st.dataframe(df_out, use_container_width=True)

            csv_bytes = df_out.to_csv(index=False).encode()
            st.download_button(
                "⬇️  Download Results CSV",
                data=csv_bytes,
                file_name="predictions.csv",
                mime="text/csv",
            )
    else:
        st.markdown("""
        <div class="upload-section">
        <b>Expected CSV format:</b><br><br>
        <code>title,brand,price</code><br>
        <code>Nike Air Max 270,Nike,150</code><br>
        <code>KitchenAid Stand Mixer 5qt,KitchenAid,399</code><br>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("#### Or try a sample dataset:")
        sample_data = pd.DataFrame({
            "title": [
                "Sony WH-1000XM5 Wireless Noise Canceling Headphones",
                "Instant Pot Duo 7-in-1 Electric Pressure Cooker 6 Qt",
                "Hydro Flask Water Bottle 32 oz Wide Mouth",
                "The Great Gatsby Paperback – F. Scott Fitzgerald",
                "Fitbit Charge 5 Advanced Fitness & Health Tracker",
            ]
        })
        if st.button("▶️  Run on Sample Data"):
            texts = sample_data["title"].tolist()
            results = []
            with st.spinner("Predicting …"):
                for text in texts:
                    preds = predict(text, model, tokenizer, i2cat, 3)
                    results.append({
                        "title": text,
                        "top_category": preds[0]["category"] if preds else "",
                        "predictions": " | ".join(f"{p['category']} ({p['score']:.1%})" for p in preds[:3]),
                    })
            st.dataframe(pd.DataFrame(results), use_container_width=True)

# ── Tab 3: Explore categories ─────────────────────────────────────────────────
with tab_explore:
    st.markdown("### 🗂️ Explore Available Categories")
    st.markdown(f"The model knows **{len(i2cat):,} categories** trained from Amazon product data.")

    search_term = st.text_input("🔎 Search categories", placeholder="e.g. Electronics, Shoes, Kitchen …")

    cats = i2cat if isinstance(i2cat, list) else list(i2cat.values())

    if search_term:
        filtered = [c for c in cats if search_term.lower() in c.lower()]
        st.markdown(f"**{len(filtered)} matches** for '{search_term}':")
        for c in filtered[:100]:
            st.markdown(f"- {c}")
        if len(filtered) > 100:
            st.info(f"Showing first 100 of {len(filtered)} matches.")
    else:
        # Show top-level categories
        roots = set()
        for c in cats:
            parts = c.split("|") if "|" in c else c.split(" > ")
            roots.add(parts[0].strip())

        roots = sorted(roots)
        st.markdown(f"**{len(roots)} top-level categories:**")
        cols = st.columns(3)
        for i, r in enumerate(roots):
            cols[i % 3].markdown(f"- {r}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Categories", f"{len(cats):,}")
    col2.metric("Training Products", "500K")
    col3.metric("Base Model", "DistilBERT")
