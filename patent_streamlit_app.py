import streamlit as st
import requests
import os
import time
from dotenv import load_dotenv
from typing import Optional

_DOTENV_LOADED = False


def _ensure_dotenv_loaded() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    try:
        # Local dev fallback only; Streamlit Community Cloud should use st.secrets/env vars.
        load_dotenv()
    except Exception:
        pass
    _DOTENV_LOADED = True


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
    if v and v.strip():
        return v.strip()

    # 3) Local .env fallback
    _ensure_dotenv_loaded()
    v = os.getenv(key)
    return (v or "").strip()


def _get_llm_api_key() -> str:
    # Compatible key names: LLM_API_KEY or OPENAI_API_KEY
    return _get_setting("LLM_API_KEY") or _get_setting("OPENAI_API_KEY")


def _init_openai_client(api_key: str, base_url: str):
    if not api_key:
        return None
    try:
        from openai import OpenAI

        if base_url:
            return OpenAI(api_key=api_key, base_url=base_url)
        return OpenAI(api_key=api_key)
    except Exception:
        return None

# 1. 页面基础配置 (必须是第一个 Streamlit 命令)
st.set_page_config(
    page_title="CNIPA 智能专利撰写系统",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. 自定义 CSS 美化 (注入灵魂)
st.markdown("""
    <style>
    /* 全局字体优化 */
    .stApp {
        font-family: "Microsoft YaHei", sans-serif;
    }
    /* 主标题样式 */
    .main-title {
        font-size: 2.5rem;
        color: #1E3A8A; /* 深蓝色，专业感 */
        font-weight: 700;
        text-align: center;
        margin-bottom: 2rem;
        padding-top: 1rem;
        border-bottom: 2px solid #E5E7EB;
        padding-bottom: 1rem;
    }
    /* 按钮样式优化 */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3.5em;
        font-weight: bold;
        background-color: #2563EB; /* 亮蓝色按钮 */
        color: white;
        border: none;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #1D4ED8; /* 悬停变深 */
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    /* 输入框标题样式 */
    .stMarkdown h3 {
        color: #374151;
        font-size: 1.1rem;
        font-weight: 600;
    }
    /* 隐藏 Streamlit 默认菜单和页脚 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# 3. 侧边栏配置 (控制台)
with st.sidebar:
    st.title("⚙️ 系统控制台")
    st.markdown("---")
    
    llm_api_key = _get_llm_api_key()
    llm_base_url = _get_setting("LLM_BASE_URL")
    llm_model = _get_setting("LLM_MODEL")
    _openai_client = _init_openai_client(llm_api_key, llm_base_url)

    if llm_api_key:
        st.success("✅ 鉴权通过（LLM_API_KEY / OPENAI_API_KEY）")
    else:
        st.info("ℹ️ 未配置 LLM 密钥（可在 Streamlit Secrets 或环境变量中配置）")

    if llm_base_url:
        st.caption(f"LLM_BASE_URL: {llm_base_url}")
    if llm_model:
        st.caption(f"LLM_MODEL: {llm_model}")

    st.markdown("###  操作指南")
    st.info(
        """
        **第一步**：填写拟申请的【专利名称】
        
        **第二步**：详细描述【技术领域】和核心创新点
        
        **第三步**：点击【立即生成】按钮
        
        **第四步**：在右侧标签页查看生成的文档
        """
    )
    st.markdown("---")
    st.caption("Version 2.0 | CNIPA AI System")

# 4. 主界面布局
st.markdown('<div class="main-title">⚖️ CNIPA 智能专利生成系统</div>', unsafe_allow_html=True)

# 创建两列布局：左边填标题，右边填领域
col1, col2 = st.columns([2, 3]) # 左2右3比例，给技术领域更多空间

with col1:
    st.markdown("###  1. 专利名称")
    st.caption("简明扼要地概括核心技术点")
    title = st.text_input("专利名称", label_visibility="collapsed", placeholder="例如：一种基于大模型的自动化代码审计方法")

with col2:
    st.markdown("###  2. 技术领域与方案")
    st.caption("请描述该专利所属领域及核心技术方案")
    tech_field = st.text_area("技术领域", label_visibility="collapsed", height=150, placeholder="例如：本发明涉及人工智能与网络安全技术领域，特别是一种利用LLM进行静态代码分析的自动化系统...")

# 5. 生成按钮逻辑
st.markdown("###") # 占位空行
generate_btn = st.button(" 立即开始生成专利文档", type="primary")

# 后端 API 地址
API_URL = _get_setting("PUBLIC_API_BASE_URL") or "http://127.0.0.1:8000"

if generate_btn:
    if not title or not tech_field:
        st.warning("⚠️ 请先补全【专利名称】和【技术领域】再开始生成。")
    else:
        # 显示加载动画
        with st.spinner(' AI 正在深度思考架构、阅读交底书并撰写文档，请稍候...'):
            try:
                # 构造请求数据（异步 job 协议：/process/text）
                payload = {
                    "title": title,
                    "technical_field": tech_field,
                    "background": "",
                    "invention_content": tech_field,
                    "embodiments": ""
                }
                
                status_line = st.empty()
                status_line.info("状态：accepted（已提交任务）")

                # 1) 提交任务
                response = requests.post(f"{API_URL}/process/text", json=payload, timeout=30)
                
                if response.status_code == 200:
                    job_info = response.json()
                    job_id = job_info.get("job_id")
                    if not job_id:
                        st.error("❌ 后端未返回 job_id，无法继续。")
                        st.json(job_info)
                        raise RuntimeError("Missing job_id in /process/text response")

                    st.success(f"✅ 任务已受理：{job_id}")

                    # 2) 轮询状态
                    status_payload = None
                    started = time.time()
                    while True:
                        elapsed = time.time() - started
                        if elapsed > 120:
                            status_line.warning("状态：timeout（等待超过 120 秒）")
                            break

                        try:
                            status_resp = requests.get(f"{API_URL}/status/{job_id}", timeout=10)
                        except Exception as e:
                            status_line.warning(f"状态：running（轮询异常：{e}）")
                            time.sleep(2)
                            continue

                        if status_resp.status_code != 200:
                            status_line.warning(f"状态：running（/status 返回 {status_resp.status_code}）")
                            time.sleep(2)
                            continue

                        status_payload = status_resp.json()
                        job_status = (status_payload.get("status") or "").lower()
                        if job_status in {"pending"}:
                            status_line.info("状态：running（pending）")
                        elif job_status in {"processing"}:
                            status_line.info("状态：running（processing）")
                        elif job_status in {"completed"}:
                            status_line.success("状态：completed（已完成）")
                            break
                        elif job_status in {"failed"}:
                            status_line.error("状态：failed（任务失败）")
                            break
                        else:
                            status_line.info(f"状态：running（{job_status or 'unknown'}）")

                        time.sleep(2)

                    # 3) 取结果：优先 status.result，否则下载产物并解析
                    result = None
                    if isinstance(status_payload, dict):
                        maybe_result = status_payload.get("result")
                        if isinstance(maybe_result, dict):
                            result = maybe_result

                    if result is None and isinstance(status_payload, dict) and (status_payload.get("status") or "").lower() == "failed":
                        st.error(status_payload.get("message") or "❌ 任务失败")
                        if status_payload.get("error"):
                            st.error(str(status_payload.get("error")))
                        raise RuntimeError("Job failed")

                    if result is None and isinstance(status_payload, dict) and (status_payload.get("status") or "").lower() == "completed":
                        dl = requests.get(f"{API_URL}/download/{job_id}", timeout=60)
                        if dl.status_code != 200:
                            st.error(f"❌ 下载结果失败：{dl.status_code}")
                            with st.expander("查看调试信息"):
                                try:
                                    st.json(dl.json())
                                except Exception:
                                    st.text(dl.text)
                            raise RuntimeError("Download failed")

                        # /download 可能返回 zip（application/zip）；从 preview/spec 解析出展示所需字段
                        import io
                        import zipfile

                        invention_content = ""
                        background = ""
                        embodiments = ""

                        def _extract_sections(text: str) -> dict:
                            sections = {"background": "", "invention_content": "", "embodiments": ""}
                            current = None
                            buf = []
                            for raw in (text or "").splitlines():
                                line = (raw or "").strip()
                                if not line:
                                    continue
                                if "背景技术" in line:
                                    if current and buf:
                                        sections[current] = "\n".join(buf).strip()
                                    current = "background"
                                    buf = []
                                    continue
                                if "发明内容" in line or "发明的内容" in line:
                                    if current and buf:
                                        sections[current] = "\n".join(buf).strip()
                                    current = "invention_content"
                                    buf = []
                                    continue
                                if "具体实施方式" in line or "实施方式" in line:
                                    if current and buf:
                                        sections[current] = "\n".join(buf).strip()
                                    current = "embodiments"
                                    buf = []
                                    continue
                                if current:
                                    buf.append(line)
                            if current and buf:
                                sections[current] = "\n".join(buf).strip()
                            return sections

                        zf = zipfile.ZipFile(io.BytesIO(dl.content))
                        preview_text = ""
                        for candidate in ["preview.md", "specification.md"]:
                            try:
                                with zf.open(candidate) as f:
                                    preview_text = f.read().decode("utf-8", errors="ignore")
                                    break
                            except Exception:
                                continue

                        if preview_text:
                            sec = _extract_sections(preview_text)
                            background = sec.get("background") or ""
                            invention_content = sec.get("invention_content") or preview_text
                            embodiments = sec.get("embodiments") or ""
                        else:
                            invention_content = "生成已完成，但无法解析预览内容（preview.md/specification.md 缺失）。"

                        result = {
                            "invention_content": invention_content,
                            "background": background,
                            "embodiments": embodiments,
                        }
                    
                    st.success(" 撰写成功！文档已生成完毕，请查看下方详情。")
                    st.markdown("---")
                    
                    # 6. 结果展示区 (使用标签页 Tab 布局)
                    tab1, tab2, tab3 = st.tabs([" 发明内容 (核心)", " 背景技术", " 具体实施方式"])
                    
                    # 辅助函数：显示带复制按钮的文本框
                    def show_result_area(content, height=500):
                        st.text_area("内容预览", value=content, height=height, label_visibility="collapsed")

                    with tab1:
                        st.markdown("#### 核心发明点摘要")
                        show_result_area(result.get("invention_content", ""))
                        
                    with tab2:
                        st.markdown("#### 现有技术背景")
                        show_result_area(result.get("background", ""))
                        
                    with tab3:
                        st.markdown("#### 具体实施方案详解")
                        show_result_area(result.get("embodiments", ""))
                        
                else:
                    st.error(f"❌ 提交失败，服务器返回错误代码: {response.status_code}")
                    with st.expander("查看调试信息"):
                        st.json(response.json())
                    
            except Exception as e:
                st.error("❌ 连接服务器失败，请检查网络或后端服务。")
                st.error(f"错误详情: {str(e)}")
