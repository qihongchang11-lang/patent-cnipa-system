import io
import json
import os
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, Tuple

import streamlit as st

# Streamlit requirement: set_page_config must be the first Streamlit command.
st.set_page_config(page_title="CNIPA Patent System", layout="wide")

# Ensure `src/` imports work on Streamlit Community Cloud
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.pse_extractor import PSEExtractor
from exporters.docx_exporter import export_patent_docx
from generators.four_piece_generator import FourPieceGenerator
from orchestrator.pipeline_orchestrator import PipelineOrchestrator, ProcessingResult


def _get_setting(key: str) -> str:
    # 1) Streamlit Cloud secrets (highest priority)
    try:
        v = st.secrets.get(key)  # type: ignore[attr-defined]
        if v is not None and str(v).strip():
            return str(v).strip()
    except Exception:
        pass

    # 2) Environment variables
    v = os.getenv(key)
    return (v or "").strip()


def _get_llm_api_key() -> str:
    # Accept either name as "auth ok"
    return _get_setting("LLM_API_KEY") or _get_setting("OPENAI_API_KEY")


def _apply_runtime_env_from_secrets() -> None:
    # Let downstream modules (e.g. utils.llm_client.LLMClient) read from os.environ.
    llm_api_key = _get_llm_api_key()
    if llm_api_key:
        os.environ["LLM_API_KEY"] = llm_api_key

    llm_base_url = _get_setting("LLM_BASE_URL")
    if llm_base_url:
        os.environ["LLM_BASE_URL"] = llm_base_url

    llm_model = _get_setting("LLM_MODEL")
    if llm_model:
        os.environ["LLM_MODEL"] = llm_model


@st.cache_resource
def _get_pipeline_components() -> Tuple[PSEExtractor, FourPieceGenerator, PipelineOrchestrator]:
    _apply_runtime_env_from_secrets()
    pse_extractor = PSEExtractor()
    generator = FourPieceGenerator()
    orchestrator = PipelineOrchestrator(enable_checks=True)
    return pse_extractor, generator, orchestrator


def _build_minimal_report(result: ProcessingResult) -> Dict[str, Any]:
    return {
        "success": bool(getattr(result, "success", False)),
        "quality_score": float(getattr(result, "quality_score", 0.0) or 0.0),
        "errors": list(getattr(result, "errors", []) or []),
        "warnings": list(getattr(result, "warnings", []) or []),
        "check_results": getattr(result, "check_results", {}) or {},
        "metadata": getattr(result, "metadata", {}) or {},
    }


def _run_monolithic_pipeline(
    *,
    title: str,
    technical_field: str,
    background: str,
    invention_content: str,
    embodiments: str,
    enable_checks: bool,
    llm_temperature: float,
) -> Tuple[bytes, Dict[str, str], Dict[str, Any]]:
    """
    Monolithic pipeline: runs everything in-process.
    Never makes any HTTP calls (no localhost dependencies).
    """
    pse_extractor, generator, orchestrator = _get_pipeline_components()

    draft_text = (
        f"发明名称：{title}\n"
        f"技术领域：{technical_field}\n"
        f"背景技术：{background}\n"
        f"发明内容：{invention_content}\n"
        f"具体实施方式：{embodiments}\n"
    )

    pse_matrix = pse_extractor.extract_from_text(draft_text)
    patent_doc = generator.generate_all(
        title=title,
        technical_field=technical_field,
        background=background,
        invention_content=invention_content,
        embodiments=embodiments,
        pse_matrix=pse_matrix,
        llm_temperature=float(llm_temperature),
    )

    result = orchestrator.process_patent(patent_doc, enable_checks=bool(enable_checks))
    report = _build_minimal_report(result)
    report["run_trace_id"] = str(uuid.uuid4())
    report["audit"] = getattr(patent_doc, "audit", {}) or {}

    docs = {
        "specification.md": (patent_doc.specification.content if patent_doc.specification else "") or "",
        "claims.md": (patent_doc.claims.content if patent_doc.claims else "") or "",
        "abstract.md": (patent_doc.abstract.content if patent_doc.abstract else "") or "",
        "disclosure.md": (patent_doc.disclosure.content if patent_doc.disclosure else "") or "",
    }

    with tempfile.TemporaryDirectory() as td:
        docx_path = Path(td) / "patent.docx"
        export_patent_docx(patent_doc, docx_path)
        docx_bytes = docx_path.read_bytes()

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in docs.items():
            zf.writestr(name, content)
        zf.writestr("quality_report.json", json.dumps(report, ensure_ascii=False, indent=2))
        zf.writestr("patent.docx", docx_bytes)

    return zip_buf.getvalue(), docs, report


def _create_zip_bytes(
    generated_results: Dict[str, str],
    report: Dict[str, Any],
    docx_bytes: bytes,
) -> bytes:
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("specification.md", (generated_results.get("specification.md") or ""))
        zf.writestr("claims.md", (generated_results.get("claims.md") or ""))
        zf.writestr("abstract.md", (generated_results.get("abstract.md") or ""))
        zf.writestr("disclosure.md", (generated_results.get("disclosure.md") or ""))
        zf.writestr("quality_report.json", json.dumps(report or {}, ensure_ascii=False, indent=2))
        if docx_bytes:
            zf.writestr("patent.docx", docx_bytes)
    return zip_buf.getvalue()


def _init_session_state() -> None:
    # Canonical persisted outputs (for edit/save)
    st.session_state.setdefault("generated_results", {})  # specification.md/claims.md/abstract.md/disclosure.md
    st.session_state.setdefault("zip_bytes", b"")
    st.session_state.setdefault("docx_bytes", b"")
    st.session_state.setdefault("quality_report", {})

    # Editor buffers (bound to widgets)
    st.session_state.setdefault("edit_specification", "")
    st.session_state.setdefault("edit_claims", "")
    st.session_state.setdefault("edit_abstract", "")
    st.session_state.setdefault("edit_disclosure", "")

    # UX state
    st.session_state.setdefault("processing_complete", False)
    st.session_state.setdefault("last_error", "")
    st.session_state.setdefault("save_message", "")


def _reset_results() -> None:
    st.session_state.generated_results = {}
    st.session_state.zip_bytes = b""
    st.session_state.docx_bytes = b""
    st.session_state.quality_report = {}
    st.session_state.edit_specification = ""
    st.session_state.edit_claims = ""
    st.session_state.edit_abstract = ""
    st.session_state.edit_disclosure = ""
    st.session_state.processing_complete = False
    st.session_state.last_error = ""
    st.session_state.save_message = ""


def _render_quality_details(report: Dict[str, Any]) -> None:
    success = bool(report.get("success", False))
    run_trace_id = str(report.get("run_trace_id", "") or "")
    errors = list(report.get("errors", []) or [])
    warnings = list(report.get("warnings", []) or [])
    check_results = report.get("check_results", {}) or {}

    st.write(f"Success: {success}")
    if run_trace_id:
        st.write(f"Run trace id: {run_trace_id}")

    if warnings:
        st.markdown("Warnings")
        st.markdown("\n".join([f"- {w}" for w in warnings]))

    if errors:
        st.markdown("Errors")
        st.markdown("\n".join([f"- {e}" for e in errors]))

    if isinstance(check_results, dict) and check_results:
        st.markdown("Checks")
        for name, res in check_results.items():
            if not isinstance(res, dict):
                continue
            st.write(f"- {name}: passed={res.get('passed')} score={res.get('score')}")
            res_errors = res.get("errors") or []
            if isinstance(res_errors, list) and res_errors:
                st.markdown("\n".join([f"  - {x}" for x in res_errors]))


_init_session_state()

st.markdown(
    """
    <style>
    .stApp { font-family: "Microsoft YaHei", sans-serif; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)


with st.sidebar:
    st.title("Control Panel")
    st.caption("Monolithic mode (no HTTP/localhost calls)")

    llm_api_key = _get_llm_api_key()
    llm_base_url = _get_setting("LLM_BASE_URL")
    llm_model = _get_setting("LLM_MODEL")

    if llm_api_key:
        st.success("Auth OK (LLM_API_KEY / OPENAI_API_KEY)")
    else:
        st.info("No LLM key configured (set in Streamlit Secrets).")

    if llm_base_url:
        st.caption(f"LLM_BASE_URL: {llm_base_url}")
    if llm_model:
        st.caption(f"LLM_MODEL: {llm_model}")

    st.slider("Creativity", min_value=0.0, max_value=1.0, value=0.2, step=0.05, key="llm_temperature")

    st.divider()
    if st.button("Reset Result", use_container_width=True):
        _reset_results()
        st.rerun()


st.markdown("## ⚖️ CNIPA Patent System")

input_col, output_col = st.columns([0.4, 0.6])

with input_col:
    st.markdown("### ✍️ Input Workspace")

    st.text_input("Title", key="input_title", placeholder="e.g., An AI-assisted patent drafting system")
    st.text_area("Technical field", key="input_technical_field", height=120)
    st.text_area("Background", key="input_background", height=120)
    st.text_area("Invention content", key="input_invention_content", height=180)
    st.text_area("Embodiments", key="input_embodiments", height=220)
    st.checkbox("Enable quality checks", key="input_enable_checks", value=True)

    st.markdown("###")
    generate_btn = st.button("Generate", type="primary", use_container_width=True)

    if generate_btn:
        title = str(st.session_state.get("input_title", "") or "").strip()
        technical_field = str(st.session_state.get("input_technical_field", "") or "").strip()
        background = str(st.session_state.get("input_background", "") or "").strip()
        invention_content = str(st.session_state.get("input_invention_content", "") or "").strip()
        embodiments = str(st.session_state.get("input_embodiments", "") or "").strip()
        enable_checks = bool(st.session_state.get("input_enable_checks", True))
        llm_temperature = float(st.session_state.get("llm_temperature", 0.2) or 0.2)

        if not title or not technical_field:
            st.warning("Please fill in Title and Technical field.")
        else:
            st.session_state.processing_complete = False
            st.session_state.last_error = ""
            st.session_state.save_message = ""
            with st.spinner("Generating draft..."):
                try:
                    zip_bytes, docs, report = _run_monolithic_pipeline(
                        title=title,
                        technical_field=technical_field,
                        background=background,
                        invention_content=invention_content or technical_field,
                        embodiments=embodiments,
                        enable_checks=enable_checks,
                        llm_temperature=llm_temperature,
                    )
                except Exception as e:
                    st.session_state.last_error = str(e)
                else:
                    st.session_state.generated_results = dict(docs or {})
                    st.session_state.quality_report = dict(report or {})
                    st.session_state.zip_bytes = zip_bytes or b""
                    # Keep patent.docx if present (for regenerated ZIP after edits)
                    try:
                        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                            st.session_state.docx_bytes = zf.read("patent.docx")
                    except Exception:
                        st.session_state.docx_bytes = b""

                    # Initialize editor buffers to generated content (overwrites previous edits on new generation)
                    st.session_state.edit_specification = st.session_state.generated_results.get("specification.md", "")
                    st.session_state.edit_claims = st.session_state.generated_results.get("claims.md", "")
                    st.session_state.edit_abstract = st.session_state.generated_results.get("abstract.md", "")
                    st.session_state.edit_disclosure = st.session_state.generated_results.get("disclosure.md", "")
                    st.session_state.processing_complete = True

with output_col:
    st.markdown("###  Review & Export")

    if st.session_state.get("last_error"):
        st.error(f"Generation failed: {st.session_state.get('last_error')}")

    report = st.session_state.get("quality_report") or {}
    docs = st.session_state.get("generated_results") or {}
    zip_bytes = st.session_state.get("zip_bytes") or b""

    score = float(report.get("quality_score", 0.0) or 0.0) if isinstance(report, dict) else 0.0
    st.metric(label="Quality Score", value=f"{score:.2f}")

    if isinstance(report, dict) and (report.get("success") is False):
        st.warning("Quality checks flagged issues, please review draft below.")

    if st.session_state.get("save_message"):
        st.success(st.session_state.get("save_message"))

    if zip_bytes:
        st.download_button(
            "Download ZIP (4 files + patent.docx + quality_report.json)",
            data=zip_bytes,
            file_name="patent_results.zip",
            mime="application/zip",
            use_container_width=True,
        )

    tab1, tab2, tab3, tab4 = st.tabs(["Specification", "Claims", "Abstract", "Disclosure"])
    with tab1:
        st.text_area("specification.md", key="edit_specification", height=600)
    with tab2:
        st.text_area("claims.md", key="edit_claims", height=600)
    with tab3:
        st.text_area("abstract.md", key="edit_abstract", height=600)
    with tab4:
        st.text_area("disclosure.md", key="edit_disclosure", height=600)

    st.markdown("###")
    save_btn = st.button("💾 Save Changes & Update ZIP", use_container_width=True)
    if save_btn:
        # Update session_state outputs from current editor buffers
        st.session_state.generated_results = {
            "specification.md": str(st.session_state.get("edit_specification", "") or ""),
            "claims.md": str(st.session_state.get("edit_claims", "") or ""),
            "abstract.md": str(st.session_state.get("edit_abstract", "") or ""),
            "disclosure.md": str(st.session_state.get("edit_disclosure", "") or ""),
        }
        st.session_state.zip_bytes = _create_zip_bytes(
            st.session_state.generated_results,
            dict(st.session_state.get("quality_report") or {}),
            bytes(st.session_state.get("docx_bytes") or b""),
        )
        st.session_state.save_message = "✅ Draft updated. Ready to download."
        st.rerun()

    with st.expander("View Quality Details"):
        if isinstance(report, dict) and report:
            _render_quality_details(report)
        else:
            st.caption("No quality report available yet.")
