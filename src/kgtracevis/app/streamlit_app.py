"""Minimal Streamlit demo entry point."""

from __future__ import annotations


def main() -> None:
    """Run a minimal Streamlit app if Streamlit is installed."""
    import streamlit as st

    st.set_page_config(page_title="KGTraceVis", layout="wide")
    st.title("KGTraceVis")
    st.write("Evidence inspection, KG correction review, and path comparison demo placeholder.")


if __name__ == "__main__":
    main()
