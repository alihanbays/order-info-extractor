#!/usr/bin/env python3
"""Streamlit demo dashboard for the ingestion pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from order_info_extractor import create_pipeline, load_config


PAGE_CSS = """
<style>
  :root {
    --bg: #f6f1e8;
    --panel: rgba(255, 252, 246, 0.92);
    --ink: #13212f;
    --muted: #5d6a73;
    --accent: #c05746;
    --accent-2: #2b6d6a;
    --border: rgba(19, 33, 47, 0.08);
  }
  .stApp {
    background:
      radial-gradient(circle at top left, rgba(192, 87, 70, 0.14), transparent 28%),
      radial-gradient(circle at top right, rgba(43, 109, 106, 0.12), transparent 26%),
      linear-gradient(180deg, #f7f2ea 0%, #efe6d8 100%);
    color: var(--ink);
  }
  [data-testid="stHeader"] { background: transparent; }
  [data-testid="stSidebar"] {
    background: rgba(255, 250, 242, 0.88);
    border-right: 1px solid var(--border);
  }
  .hero {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 24px;
    padding: 2rem 2rem 1.75rem;
    box-shadow: 0 24px 60px rgba(19, 33, 47, 0.08);
    backdrop-filter: blur(16px);
  }
  .hero h1 {
    font-family: "Avenir Next", "Helvetica Neue", sans-serif;
    font-size: 2.4rem;
    line-height: 1.05;
    margin-bottom: 0.5rem;
    color: var(--ink);
    letter-spacing: -0.03em;
  }
  .hero p {
    color: var(--muted);
    font-size: 1rem;
    max-width: 48rem;
  }
  .pill {
    display: inline-block;
    background: rgba(43, 109, 106, 0.1);
    color: var(--accent-2);
    border-radius: 999px;
    padding: 0.25rem 0.7rem;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .section-card {
    background: rgba(255, 252, 246, 0.94);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 1.25rem 1.25rem 1rem;
    box-shadow: 0 20px 40px rgba(19, 33, 47, 0.05);
  }
  .label {
    color: var(--muted);
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.35rem;
  }
  .stMetric {
    background: rgba(255, 252, 246, 0.94);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 0.85rem 1rem;
  }
  .stMetric [data-testid="stMetricValue"] {
    color: var(--ink);
    font-family: "Avenir Next", "Helvetica Neue", sans-serif;
  }
  .stButton > button, .stDownloadButton > button {
    border-radius: 14px !important;
    border: none !important;
    background: linear-gradient(135deg, #c05746, #b26c35) !important;
    color: white !important;
    font-weight: 700 !important;
  }
  .status-badge {
    display: inline-block;
    border-radius: 999px;
    padding: 0.3rem 0.65rem;
    font-size: 0.78rem;
    font-weight: 700;
  }
  .status-approved { background: rgba(43, 109, 106, 0.13); color: var(--accent-2); }
  .status-review { background: rgba(192, 87, 70, 0.13); color: var(--accent); }
</style>
"""


def _load_results():
    config = load_config()
    pipeline = create_pipeline(config)
    return config, pipeline.run(force=True)


def _orders_frame(summary):
    rows = []
    for processed in summary.processed_orders:
        extraction = processed.extraction
        rows.append(
            {
                "message_id": processed.message_id,
                "status": processed.status,
                "confidence": processed.confidence,
                "customer": extraction.customer_name if extraction else "",
                "account": extraction.account_number if extraction else "",
                "items": len(extraction.line_items) if extraction else 0,
                "parser": extraction.parser_name if extraction else "",
            }
        )
    return rows


def _review_cases(summary):
    cases = []
    for processed in summary.processed_orders:
        if processed.status != "manual_review":
            continue
        issue_text = ", ".join(issue.code for issue in processed.validation_issues)
        cases.append(
            {
                "message_id": processed.message_id,
                "customer": processed.extraction.customer_name if processed.extraction else "",
                "confidence": processed.confidence,
                "issues": issue_text,
                "review_path": processed.review_path,
            }
        )
    return cases


def main() -> None:
    st.set_page_config(
        page_title="Order Ingestion Pipeline Demo",
        page_icon="📦",
        layout="wide",
    )
    st.markdown(PAGE_CSS, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### Demo Controls")
        rerun = st.button("Run Fixture Pipeline", use_container_width=True)
        st.caption(
            "The public demo runs against sanitized mock Outlook messages and a fixture-backed LLM response set."
        )

    if "summary" not in st.session_state or rerun:
        config, summary = _load_results()
        st.session_state["config"] = config
        st.session_state["summary"] = summary

    config = st.session_state["config"]
    summary = st.session_state["summary"]

    st.markdown(
        """
        <section class="hero">
          <span class="pill">Public Demo</span>
          <h1>Reliable Order Ingestion From Mock Outlook Messages</h1>
          <p>
            This dashboard showcases a resume-ready pipeline with typed config, idempotent processing,
            confidence scoring, catalog validation, ERP export generation, structured JSON logs, and a
            manual-review queue for ambiguous orders.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.write("")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Approved Orders", summary.approved_count)
    c2.metric("Manual Review", summary.review_count)
    c3.metric("Skipped Duplicates", summary.skipped_count)
    c4.metric("Run ID", summary.run_id)

    left, right = st.columns([1.4, 1])
    with left:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="label">Processed Messages</div>', unsafe_allow_html=True)
        st.dataframe(_orders_frame(summary), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if summary.export_path:
            export_path = Path(summary.export_path)
            st.write("")
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="label">ERP Export Preview</div>', unsafe_allow_html=True)
            st.code(export_path.read_text(), language="text")
            st.download_button(
                label="Download ERP Export",
                data=export_path.read_text(),
                file_name=export_path.name,
                mime="text/plain",
                use_container_width=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="label">Runtime Surface</div>', unsafe_allow_html=True)
        st.write(f"Catalog: `{config.catalog_path}`")
        st.write(f"Source provider: `{config.source.provider}`")
        st.write(f"Confidence threshold: `{config.confidence_threshold}`")
        st.write(f"Artifacts root: `{config.paths.output_root}`")
        st.markdown("</div>", unsafe_allow_html=True)

        st.write("")
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="label">Manual Review Queue</div>', unsafe_allow_html=True)
        review_frame = _review_cases(summary)
        if not review_frame:
            st.info("No review cases in the current run.")
        else:
            st.dataframe(review_frame, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.write("")
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="label">Run Manifest</div>', unsafe_allow_html=True)
        if summary.manifest_path:
            st.code(Path(summary.manifest_path).read_text(), language="json")
        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
