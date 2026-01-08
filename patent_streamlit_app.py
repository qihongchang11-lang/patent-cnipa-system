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

# Page Config (must be the first Streamlit command)
st.set_page_config(page_title="CNIPA 智能专利生成系统 (车间科研版)", layout="wide", page_icon="⚖️")

# Ensure `src/` imports work on Streamlit Community Cloud
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.pse_extractor import PSEExtractor
from exporters.docx_exporter import export_patent_docx
from generators.four_piece_generator import FourPieceGenerator
from orchestrator.pipeline_orchestrator import PipelineOrchestrator, ProcessingResult


# -----------------------
# Styling (Industrial UI)
# -----------------------
st.markdown(
    """
<style>
/* Hide Streamlit chrome */
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}

/* Center titles */
h1 { text-align: center; }
.subtitle { text-align: center; color: gray; margin-bottom: 2em; }

/* Block-style tabs */
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] {
  flex-grow: 1;
  text-align: center;
  font-weight: 800;
  border-radius: 10px;
  background: #E5E7EB;
  color: #111827;
  border: 1px solid #CBD5E1;
}
.stTabs [data-baseweb="tab"] > div { justify-content: center; }
.stTabs [data-baseweb="tab"][aria-selected="true"] {
  background: #1E3D59;
  color: #FFFFFF;
  border: 1px solid #1E3D59;
}
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------
# Helpers / Core Pipeline
# -----------------------
def _get_setting(key: str) -> str:
    try:
        v = st.secrets.get(key)  # type: ignore[attr-defined]
        if v is not None and str(v).strip():
            return str(v).strip()
    except Exception:
        pass
    return (os.getenv(key) or "").strip()


def _get_llm_api_key() -> str:
    return _get_setting("LLM_API_KEY") or _get_setting("OPENAI_API_KEY")


def _apply_runtime_env_from_secrets() -> None:
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
    return PSEExtractor(), FourPieceGenerator(), PipelineOrchestrator(enable_checks=True)


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


def _create_zip_bytes(generated_results: Dict[str, str], report: Dict[str, Any], docx_bytes: bytes) -> bytes:
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("claims.md", generated_results.get("claims.md", ""))
        zf.writestr("specification.md", generated_results.get("specification.md", ""))
        zf.writestr("abstract.md", generated_results.get("abstract.md", ""))
        zf.writestr("disclosure.md", generated_results.get("disclosure.md", ""))
        zf.writestr("quality_report.json", json.dumps(report or {}, ensure_ascii=False, indent=2))
        if docx_bytes:
            zf.writestr("patent.docx", docx_bytes)
    return zip_buf.getvalue()


def _init_session_state() -> None:
    st.session_state.setdefault("generated_results", {})
    st.session_state.setdefault("zip_bytes", b"")
    st.session_state.setdefault("docx_bytes", b"")
    st.session_state.setdefault("quality_report", {})
    st.session_state.setdefault("processing_complete", False)
    st.session_state.setdefault("last_error", "")


_init_session_state()


# -----------------------
# Header
# -----------------------
st.markdown("<h1 style='text-align: center;'>国家知识产权局专利自动生成系统</h1>", unsafe_allow_html=True)
st.markdown(
    "<p class='subtitle'>专注车间科技转化 · 助力一线创新实践</p>",
    unsafe_allow_html=True,
)


# -----------------------
# Sidebar (系统参数设置)
# -----------------------
with st.sidebar:
    st.markdown("## ⚙️ 系统参数设置")
    st.slider(
        "创新发散度 (Temperature)",
        min_value=0.0,
        max_value=1.0,
        value=0.2,
        step=0.05,
        key="llm_temperature",
        help="0.2=严谨模式(权利要求); 0.5=发散模式(背景技术)",
    )
    st.info("当前内核: DeepSeek V3 (商业版)")


# -----------------------
# Main Layout (Split View)
# -----------------------
col_input, col_output = st.columns([0.4, 0.6])


# -----------------------
# Left: 撰写工作台
# -----------------------
with col_input:
    st.markdown("### ✍️ 撰写工作台")
    inv_title = st.text_input("发明名称", key="input_title")
    domain = st.text_input("所属技术领域", key="input_technical_field", placeholder="例如：卷烟包装设备、视觉检测")
    bg = st.text_area(
        "背景技术（现有技术痛点）",
        key="input_background",
        height=150,
        placeholder="请描述当前技术或工艺存在的主要痛点。例如：人工效率低、废品率高、设备故障频繁...",
    )
    inv_content = st.text_area(
        "发明内容（核心技术方案）",
        key="input_invention_content",
        height=200,
        placeholder="请详细描述您的改进方案。例如：增加了XX结构、采用了XX算法、优化了XX流程...",
    )
    impl = st.text_area("具体实施方式（可选）", key="input_embodiments", height=100)

    st.markdown("###")
    generate_btn = st.button(" 开始生成专利申请草稿", type="primary", use_container_width=True)

    if generate_btn:
        title = (inv_title or "").strip()
        technical_field = (domain or "").strip()
        background = (bg or "").strip()
        invention_content = (inv_content or "").strip()
        embodiments = (impl or "").strip()
        llm_temperature = float(st.session_state.get("llm_temperature", 0.2) or 0.2)

        if not title or not technical_field:
            st.warning("请先填写【发明名称】与【所属技术领域】。")
        else:
            st.session_state.last_error = ""
            st.session_state.processing_complete = False
            with st.spinner("正在生成草稿并执行质检..."):
                try:
                    zip_bytes, docs, report = _run_monolithic_pipeline(
                        title=title,
                        technical_field=technical_field,
                        background=background,
                        invention_content=invention_content or technical_field,
                        embodiments=embodiments,
                        enable_checks=True,
                        llm_temperature=llm_temperature,
                    )
                except Exception as e:
                    st.session_state.last_error = str(e)
                else:
                    st.session_state.generated_results = dict(docs or {})
                    st.session_state.quality_report = dict(report or {})
                    st.session_state.zip_bytes = zip_bytes or b""
                    try:
                        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                            st.session_state.docx_bytes = zf.read("patent.docx")
                    except Exception:
                        st.session_state.docx_bytes = b""
                    st.session_state.processing_complete = True
                    st.toast("✅ 生成完成，可在右侧编辑与导出。")


# -----------------------
# Right: 生成结果与质检
# -----------------------
with col_output:
    st.markdown("### 🧪 生成结果与质检")

    if st.session_state.get("last_error"):
        st.error(f"生成失败：{st.session_state.get('last_error')}")

    if not st.session_state.get("generated_results"):
        st.info(" 请在左侧工作台输入技术方案并启动生成。")
    else:
        report = st.session_state.get("quality_report") or {}
        score = float((report or {}).get("quality_score", 0.0) or 0.0)
        st.success(f"✅ 状态：生成完成 | 综合评分：{score:.2f}")

        gen = st.session_state.get("generated_results") or {}

        tab_claims, tab_spec, tab_abs, tab_dis = st.tabs(["权利要求书", "说明书", "说明书摘要", "技术交底书"])
        with tab_claims:
            st.text_area("权利要求书（可编辑）", value=gen.get("claims.md", ""), key="widget_claims", height=600)
        with tab_spec:
            st.text_area("说明书（可编辑）", value=gen.get("specification.md", ""), key="widget_spec", height=600)
        with tab_abs:
            st.text_area("说明书摘要（可编辑）", value=gen.get("abstract.md", ""), key="widget_abs", height=600)
        with tab_dis:
            st.text_area("技术交底书（可编辑）", value=gen.get("disclosure.md", ""), key="widget_dis", height=600)

        st.markdown("###")
        col_save, col_dl = st.columns(2)
        with col_save:
            if st.button(" 保存修改并更新压缩包", type="secondary", use_container_width=True):
                st.session_state.generated_results = {
                    "claims.md": str(st.session_state.get("widget_claims", "") or ""),
                    "specification.md": str(st.session_state.get("widget_spec", "") or ""),
                    "abstract.md": str(st.session_state.get("widget_abs", "") or ""),
                    "disclosure.md": str(st.session_state.get("widget_dis", "") or ""),
                }
                st.session_state.zip_bytes = _create_zip_bytes(
                    st.session_state.generated_results,
                    dict(st.session_state.get("quality_report") or {}),
                    bytes(st.session_state.get("docx_bytes") or b""),
                )
                st.success("✅ Draft updated. Ready to download.")
        with col_dl:
            st.download_button(
                " 下载申报材料 (ZIP)",
                data=st.session_state.get("zip_bytes") or b"",
                file_name="patent_results.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True,
                disabled=not bool(st.session_state.get("zip_bytes")),
            )

st.markdown(
    "<p style='text-align: center; color: #6B7280; margin-top: 2em;'>© 2026 宁波卷烟厂 | 内部科研专用系统</p>",
    unsafe_allow_html=True,
)
