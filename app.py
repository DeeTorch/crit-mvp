import streamlit as st
import asyncio
import os
import textwrap
from crit_orchestrator import (
    run_pipeline_on_elements,
    parse_ast_elements,
    CritConfig,
    ASTParsingError,
    get_git_diff_mapping,
    extract_skeleton,
    scrub_sensitive_data,
)

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CRIT Audit Dashboard",
    page_icon="🚀",
    layout="wide",
)

# ── Sidebar / Controls (Col 1) ────────────────────────────────────────────────
st.sidebar.title("🚀 CRIT Controls")
st.sidebar.markdown("---")

uploaded_file = st.sidebar.file_uploader("Upload Python File", type=["py"])
diff_mode = st.sidebar.toggle("Diff-Aware Mode", value=False)

st.sidebar.subheader("Configuration")
min_score = st.sidebar.slider("Min Pass Score", 0.0, 10.0, 7.0)
metrics = st.sidebar.multiselect(
    "Evaluation Metrics",
    ["Readability", "Robustness", "Security", "Performance", "Documentation"],
    default=["Readability", "Robustness", "Security"],
)
custom_instr = st.sidebar.text_area("Custom Instructions", placeholder="e.g., Favor strict typing.")

run_audit = st.sidebar.button("Run Audit", type="primary", use_container_width=True)

st.sidebar.markdown("---")
privacy_preview = st.sidebar.checkbox("🛡️ Privacy Shield Preview", value=False)

# ── Layout: 2 Main Columns ───────────────────────────────────────────────────
col2, col3 = st.columns([1, 1])

# Global state for audit results
if "audit_result" not in st.session_state:
    st.session_state.audit_result = None

# ── Logic: Run Audit ──────────────────────────────────────────────────────────
if run_audit and uploaded_file:
    source_code = uploaded_file.getvalue().decode("utf-8")
    filename = uploaded_file.name
    
    # Save temporary file for AST resolution if needed
    with open(filename, "w", encoding="utf-8") as f:
        f.write(source_code)
    
    config = CritConfig(
        min_pass_score=min_score,
        evaluation_metrics=metrics,
        custom_instructions=custom_instr,
    )
    
    target_lines = None
    if diff_mode:
        diff_map = get_git_diff_mapping(staged_only=False)
        target_norm = os.path.relpath(filename).replace("\\", "/")
        target_lines = diff_map.get(target_norm)
        if target_lines is None:
            st.warning(f"No changes detected in {filename} for Diff Mode.")
    
    try:
        with st.spinner("🌳 Parsing AST and Dependencies..."):
            elements = parse_ast_elements(source_code, filename, target_lines=target_lines)
        
        with st.spinner("🚀 Running Map-Reduce Pipeline..."):
            verdict, analyses = asyncio.run(
                run_pipeline_on_elements(elements, filename, config, is_diff_mode=diff_mode)
            )
            st.session_state.audit_result = (verdict, analyses, source_code)
            st.success("Audit Complete!")
            
    except ASTParsingError as e:
        st.error(f"AST Parsing Failed: {e.message}")
    except Exception as e:
        st.error(f"Pipeline Error: {e}")
    finally:
        if os.path.exists(filename):
            os.remove(filename)

# ── Col 2: Audit View ─────────────────────────────────────────────────────────
with col2:
    st.header("📊 Audit Findings")
    if st.session_state.audit_result:
        verdict, analyses, _ = st.session_state.audit_result
        
        # Executive Summary Card
        score_color = "green" if verdict.overall_score >= min_score else "red"
        st.markdown(f"""
        ### Executive Summary
        | Metric | Value |
        | :--- | :--- |
        | **Overall Score** | :{score_color}[{verdict.overall_score:.1f} / 10.0] |
        | **Grade** | **{verdict.grade}** |
        | **Elements** | {verdict.element_count} |
        """)
        
        st.info(f"**Recommendation:** {verdict.recommendation}")
        
        # Strengths & Weaknesses
        s_col, w_col = st.columns(2)
        with s_col:
            st.success("**Strengths**")
            for s in verdict.top_strengths:
                st.markdown(f"- {s}")
        with w_col:
            st.error("**Weaknesses**")
            for w in verdict.top_weaknesses:
                st.markdown(f"- {w}")
                
        st.divider()
        
        # Element Breakdown
        st.subheader("Element Breakdown")
        for a in analyses:
            with st.expander(f"`{a.element_name}` ({a.element_type})"):
                st.write(a.summary)
                st.table([
                    {"Criterion": s.criterion, "Score": s.score, "Severity": s.severity.value, "Rationale": s.rationale}
                    for s in a.scores
                ])
    else:
        st.info("Upload a file and click 'Run Audit' to see results.")

# ── Col 3: Code View ──────────────────────────────────────────────────────────
with col3:
    st.header("📝 Source Code")
    
    current_source = ""
    if st.session_state.audit_result:
        _, _, current_source = st.session_state.audit_result
    elif uploaded_file:
        current_source = uploaded_file.getvalue().decode("utf-8")

    if privacy_preview and current_source:
        tab_raw, tab_payload = st.tabs(["📄 Raw Code", "🔒 Transmitted Payload"])
        
        with tab_raw:
            st.code(current_source, language="python", line_numbers=True)
            
        with tab_payload:
            st.markdown("""
            > [!NOTE]  
            > This view shows exactly what is transmitted to the LLM. 
            > Bodies are stripped (Skeletonization) and PII is redacted locally.
            """)
            
            # Generate transmitted payload preview
            # 1. Save temp file for skeletonization
            tmp_filename = "preview_tmp.py"
            try:
                with open(tmp_filename, "w", encoding="utf-8") as f:
                    f.write(current_source)
                
                skeleton = extract_skeleton(tmp_filename) or "# Failed to generate skeleton"
                redacted_payload = scrub_sensitive_data(skeleton)
                st.code(redacted_payload, language="python", line_numbers=True)
            finally:
                if os.path.exists(tmp_filename):
                    os.remove(tmp_filename)
    elif current_source:
        st.code(current_source, language="python", line_numbers=True)
    else:
        st.info("No code to display.")
