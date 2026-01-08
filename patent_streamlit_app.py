import io
import json
import os
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import streamlit as st


# Ensure `src/` imports work on Streamlit Community Cloud
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.pse_extractor import PSEExtractor
from exporters.docx_exporter import export_patent_docx
from generators.four_piece_generator import FourPieceGenerator
from orchestrator.pipeline_orchestrator import PipelineOrchestrator, ProcessingResult


def _get_setting(key: str) -> str:
    # 1) Streamlit Cloud secrets
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
    return _get_setting("LLM_API_KEY") or _get_setting("OPENAI_API_KEY")


def _apply_runtime_env_from_secrets() -> None:
    """
    Make downstream modules (e.g. utils.llm_client.LLMClient) pick up Streamlit secrets.
    This avoids any dependency on a local `.env` file in production.
    """
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
) -> Tuple[bytes, Dict[str, str], Dict[str, Any]]:
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
        zf.writestr("specification.md", docs["specification.md"])
        zf.writestr("claims.md", docs["claims.md"])
        zf.writestr("abstract.md", docs["abstract.md"])
        zf.writestr("disclosure.md", docs["disclosure.md"])
        zf.writestr("quality_report.json", json.dumps(report, ensure_ascii=False, indent=2))
        zf.writestr("patent.docx", docx_bytes)

    return zip_buf.getvalue(), docs, report


st.set_page_config(
    page_title="CNIPA 智能专利生成系统",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
    st.title("⚙️ 系统控制台")
    st.markdown("---")

    llm_api_key = _get_llm_api_key()
    llm_base_url = _get_setting("LLM_BASE_URL")
    llm_model = _get_setting("LLM_MODEL")

    if llm_api_key:
        st.success("✅ 鉴权通过（LLM_API_KEY / OPENAI_API_KEY）")
    else:
        st.info("ℹ️ 未配置 LLM 密钥（可在 Streamlit Secrets 中配置）")

    if llm_base_url:
        st.caption(f"LLM_BASE_URL: {llm_base_url}")
    if llm_model:
        st.caption(f"LLM_MODEL: {llm_model}")

    st.markdown("---")
    st.markdown("### 操作指南")
    st.info("填写内容后点击【立即生成】。本版本为单体化架构：不再访问任何 localhost/HTTP API。")


st.markdown("## ⚖️ CNIPA 智能专利生成系统（单体化）")

col1, col2 = st.columns([2, 3])
with col1:
    title = st.text_input("专利名称", placeholder="例如：一种基于大模型的自动化专利撰写方法")
    enable_checks = st.checkbox("启用质量检查", value=True)

with col2:
    technical_field = st.text_area("技术领域", height=120, placeholder="例如：本发明涉及……")

background = st.text_area("背景技术", height=120, placeholder="现有技术存在的问题……")
invention_content = st.text_area("发明内容", height=180, placeholder="本发明的技术方案与有益效果……")
embodiments = st.text_area("具体实施方式", height=220, placeholder="实施例/步骤/结构细节……")

st.markdown("###")
generate_btn = st.button("立即生成四件套（本地计算，无HTTP）", type="primary", use_container_width=True)

if generate_btn:
    if not title.strip() or not technical_field.strip():
        st.warning("⚠️ 请先补全【专利名称】和【技术领域】。")
    else:
        with st.spinner("正在生成四件套并执行检查，请稍候..."):
            try:
                zip_bytes, docs, report = _run_monolithic_pipeline(
                    title=title.strip(),
                    technical_field=technical_field.strip(),
                    background=background.strip(),
                    invention_content=(invention_content.strip() or technical_field.strip()),
                    embodiments=embodiments.strip(),
                    enable_checks=bool(enable_checks),
                )
            except Exception as e:
                st.error(f"❌ 生成失败：{e}")
            else:
                st.success(f"✅ 生成完成 | 质量分：{report.get('quality_score', 0.0):.2f}")

                st.download_button(
                    "下载产物 zip（四件套 + patent.docx + quality_report.json）",
                    data=zip_bytes,
                    file_name="patent_results.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

                tab1, tab2, tab3, tab4, tab5 = st.tabs(["说明书", "权利要求书", "摘要", "披露", "质量报告"])
                with tab1:
                    st.text_area("specification.md", value=docs.get("specification.md", ""), height=520)
                with tab2:
                    st.text_area("claims.md", value=docs.get("claims.md", ""), height=520)
                with tab3:
                    st.text_area("abstract.md", value=docs.get("abstract.md", ""), height=520)
                with tab4:
                    st.text_area("disclosure.md", value=docs.get("disclosure.md", ""), height=520)
                with tab5:
                    st.json(report)
