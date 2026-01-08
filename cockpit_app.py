import streamlit as st
import requests
import os
import time
from dotenv import load_dotenv

# --- 1. 座舱基础配置 ---
st.set_page_config(
    page_title="CNIPA 智能生产座舱",
    page_icon="️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 尝试加载环境变量，如果失败则静默（依赖 Docker 注入）
try:
    load_dotenv()
except:
    pass

# --- 2. 注入座舱专属 CSS (科技感/深色模式适配) ---
st.markdown("""
    <style>
    .stApp { font-family: "Microsoft YaHei", sans-serif; }
    
    /* 顶部状态栏样式 */
    .status-bar {
        padding: 12px 20px;
        background-color: #f0f9ff;
        border-radius: 8px;
        margin-bottom: 20px;
        border-left: 6px solid #0ea5e9; /* 天蓝色 */
        color: #0c4a6e;
        font-weight: 600;
        font-size: 1.05rem;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }
    
    /* 隐藏默认元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 增强 Tabs 样式 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 20px;
        margin-top: 20px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 45px;
        background-color: transparent;
        font-weight: 600;
        color: #64748b;
    }
    .stTabs [aria-selected="true"] {
        color: #0284c7;
        border-bottom-color: #0284c7;
    }
    
    /* 按钮样式增强 */
    div.stButton > button {
        background-color: #0284c7;
        color: white;
        border: none;
        height: 50px;
        font-size: 16px;
        transition: all 0.3s;
    }
    div.stButton > button:hover {
        background-color: #0369a1;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    </style>
""", unsafe_allow_html=True)

# --- 3. 侧边栏：生产监控日志 ---
with st.sidebar:
    st.image("[https://img.icons8.com/fluency/96/console.png](https://img.icons8.com/fluency/96/console.png)", width=50)
    st.title("生产监控台")
    st.caption("System Status: Online | V3.0")
    st.divider()
    
    # 模拟系统日志区
    log_container = st.container()
    
    # 检查 API 连接
    api_key = os.getenv("API_KEY")
    with log_container:
        if api_key:
            st.success(" [SYSTEM] API Link: Connected")
        else:
            st.error(" [SYSTEM] API Key Missing")
        st.info(" [KERNEL] DeepSeek-V3 Ready")

    st.divider()
    st.markdown("### ️ 任务参数")
    st.text("生成模式: 标准流水线")
    st.text("输出格式: CNIPA 标准")

# --- 4. 主座舱布局 ---
st.markdown("## ️ CNIPA 专利智能生产座舱")

# 顶部状态栏 (Status Pipeline)
status_placeholder = st.empty()
status_placeholder.markdown('<div class="status-bar">⚪ 系统就绪 | 等待任务指令...</div>', unsafe_allow_html=True)

# 输入区域
col1, col2 = st.columns([1, 2])
with col1:
    st.markdown("#####  1. 任务名称")
    title = st.text_input("title", label_visibility="collapsed", placeholder="输入专利名称...")
with col2:
    st.markdown("#####  2. 技术交底数据")
    tech_field = st.text_area("tech", label_visibility="collapsed", height=100, placeholder="在此输入核心技术方案、创新点...")

# 启动按钮
st.markdown("###")
start_btn = st.button("⚡ 启动生产流水线 (Start Pipeline)", type="primary", use_container_width=True)

API_URL = os.getenv("PUBLIC_API_BASE_URL", "http://api:8000")

# --- 5. 核心逻辑：分步可视化的“假象” ---
if start_btn:
    if not title or not tech_field:
        st.warning("⚠️ 任务指令不完整，请补充名称和技术方案")
    else:
        # 1. 改变状态栏
        status_placeholder.markdown('<div class="status-bar" style="border-left-color: #f59e0b; background-color: #fffbeb; color: #92400e;"> [PROCESSING] 正在执行智能撰写流水线...</div>', unsafe_allow_html=True)
        
        # 2. 清空并初始化日志
        with log_container:
            st.write(f" [TASK] 接收任务: {title[:8]}...")
            time.sleep(0.5)
        
        # 3. 启动分步模拟
        with st.status(" 正在初始化 AI 生产环境...", expanded=True) as status:
            
            # 步骤 A: 模拟解析
            st.write("⚙️ 正在解析技术交底书数据结构...")
            time.sleep(1) 
            with log_container:
                st.write(" [SEARCH] 检索相关分类号...")
            st.write(" 正在建立与 DeepSeek 大模型的安全连接...")
            time.sleep(1)
            
            # 步骤 B: 真实调用 (API请求)
            st.write(" DeepSeek 正在构建权利要求逻辑树 (预计耗时 30-60秒)...")
            
            try:
                # 真实请求
                payload = {"title": title, "technical_field": tech_field, "background": "", "embodiments": "", "claims": ""}
                response = requests.post(f"{API_URL}/generate_patent", json=payload, timeout=120)
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # 步骤 C: 模拟“组装”过程
                    st.write("✅ 核心逻辑构建完成")
                    with log_container:
                        st.write("✅ [DONE] Claims Generated")
                    time.sleep(0.5)
                    
                    st.write("✍️ 正在撰写说明书摘要与背景技术...")
                    with log_container:
                        st.write("✅ [DONE] Summary Generated")
                    time.sleep(0.5)
                    
                    st.write(" 正在填充具体实施方式细节...")
                    
                    # 完成状态
                    status.update(label="✨ 生产完成！文档已装配完毕", state="complete", expanded=False)
                    
                    status_placeholder.markdown('<div class="status-bar" style="border-left-color: #22c55e; background-color: #dcfce7; color: #15803d;">✅ [COMPLETE] 任务完成 | 文档已就绪 | 等待检视</div>', unsafe_allow_html=True)
                    
                    # --- 6. 结果展示：座舱仪表盘 ---
                    st.divider()
                    
                    tab1, tab2, tab3 = st.tabs([" 权利要求书 (Claims)", " 说明书摘要 (Summary)", " 具体实施方式 (Detail)"])
                    
                    with tab1:
                        st.caption("法律保护范围的核心定义")
                        st.text_area("claims", value=result.get("claims", "生成内容解析中..."), height=500, label_visibility="collapsed")
                    with tab2:
                        st.caption("技术方案的宏观概述")
                        st.text_area("invention", value=result.get("invention_content", ""), height=500, label_visibility="collapsed")
                    with tab3:
                        st.caption("技术方案的详细落地实现")
                        st.text_area("embodiments", value=result.get("embodiments", ""), height=500, label_visibility="collapsed")
                        
                    with log_container:
                        st.success(" [FINISH] 流水线结束")
                        
                else:
                    status.update(label="❌ 生产中断", state="error")
                    st.error(f"服务器返回错误: {response.status_code}")
                    status_placeholder.markdown('<div class="status-bar" style="border-left-color: #ef4444; background-color: #fef2f2; color: #991b1b;">❌ [ERROR] 生产异常</div>', unsafe_allow_html=True)
                    
            except Exception as e:
                status.update(label="❌ 连接中断", state="error")
                st.error(f"连接失败: {str(e)}")
                status_placeholder.markdown('<div class="status-bar" style="border-left-color: #ef4444; background-color: #fef2f2; color: #991b1b;">❌ [ERROR] 网络中断</div>', unsafe_allow_html=True)
