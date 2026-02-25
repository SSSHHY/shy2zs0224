import streamlit as st
import pandas as pd
import plotly.express as px

# ==========================================
# 1. 页面配置与全局样式
# ==========================================
st.set_page_config(
    page_title="医疗器械采购智能分析平台", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main .block-container { overflow-y: auto !important; }
    html, body, [data-testid="stAppViewContainer"] { overflow: visible !important; }
    .stMetric { background-color: #f0f2f6; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 核心处理函数 (数据逻辑层)
# ==========================================

def load_data_old(file):
    """旧版模式：加载多月份计划表"""
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, skiprows=3)
        else:
            df = pd.read_excel(file, skiprows=3, engine=engine)
        
        # 解决重复列名问题
        df.columns = [f"{c}_{i}" if list(df.columns).count(c) > 1 else c for i, c in enumerate(df.columns)]
        
        # 基础清洗
        df = df.dropna(subset=['产品名称'])
        df['所属月份'] = file.name.split('.')[0]
        
        # 数值转换
        num_cols = ['数量', '金额', '供应医院价格（单位：元）']
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 文本清洗
        str_cols = ['产品名称', '型号', '规格']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).replace('nan', '-')
                
        return df
    except Exception as e:
        st.error(f"解析文件 {file.name} 失败: {e}")
        return None

def load_data_new_smart(file):
    """新版模式：智能识别表头并统一字段"""
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        df_raw = pd.read_excel(file, header=None, engine=engine) if not file.name.endswith('.csv') else pd.read_csv(file, header=None)
        
        # 智能定位表头：搜索包含关键词的行
        header_idx = 0
        keywords = ["产品名称", "耗材名称", "规格型号", "型号"]
        for i, row in df_raw.head(20).iterrows():
            if any(k in str(val) for val in row.values for k in keywords):
                header_idx = i
                break
        
        df = df_raw.iloc[header_idx:].copy()
        df.columns = df.iloc[0]
        df = df[1:].reset_index(drop=True)
        
        # 字段映射表
        name_map = {
            '耗材名称': '产品名称', 
            '结存数量': '仓库库存', 
            '库存数量': '仓库库存',
            '生产厂商': '生产厂商', 
            '厂商': '生产厂商'
        }
        df.rename(columns=lambda x: name_map.get(str(x).strip(), str(x).strip()), inplace=True)
        
        # 自动转换数值列
        if '数量' in df.columns:
            df['数量'] = pd.to_numeric(df['数量'], errors='coerce').fillna(0)
        if '仓库库存' in df.columns:
            df['仓库库存'] = pd.to_numeric(df['仓库库存'], errors='coerce').fillna(0)
            
        return df
    except Exception as e:
        st.error(f"智能解析文件 {file.name} 出错: {e}")
        return None

# ==========================================
# 3. 侧边栏与导航
# ==========================================
st.sidebar.title("🛠️ 控制面板")
mode = st.sidebar.radio(
    "选择分析模式",
    ["旧版：多月计划对比", "新版：计划/仓库联动"],
    help="旧版侧重纵向时间对比，新版侧重横向库存匹配。"
)

st.sidebar.markdown("---")

# ==========================================
# 4. 主界面逻辑
# ==========================================
st.title("🏥 医疗器械采购计划智能分析平台")

if mode == "旧版：多月计划对比":
    st.sidebar.subheader("📁 上传多月数据")
    uploaded_files = st.sidebar.file_uploader("支持批量上传 (xlsx, xls, csv)", accept_multiple_files=True)

    if uploaded_files:
        all_dfs = [load_data_old(f) for f in uploaded_files]
        all_dfs = [d for d in all_dfs if d is not None]
        
        if all_dfs:
            full_df = pd.concat(all_dfs, ignore_index=True)
            months = sorted(full_df['所属月份'].unique())
            num_m = len(months)
            
            # 分析配置
            target_col = st.sidebar.selectbox("分析指标", ["数量", "金额"])
            
            # --- 指标卡展示 ---
            st.subheader("📊 全周期核心指标")
            c1, c2, c3 = st.columns(3)
            total_items = full_df['产品名称'].nunique()
            total_val = full_df[target_col].sum()
            
            c1.metric("总品种数", f"{total_items} 种")
            c2.metric(f"累计总{target_col}", f"{total_val:,.2f}")
            c3.metric(f"月均单品{target_col}", f"{(total_val / num_m / total_items):,.2f}" if total_items > 0 else 0)

            # --- 透视对比分析 ---
            st.divider()
            st.subheader(f"🔍 各产品【{target_col}】趋势对比")
            
            pivot_df = full_df.pivot_table(
                index=['产品名称', '型号'], 
                columns='所属月份', 
                values=target_col, 
                aggfunc='sum'
            ).fillna(0)
            
            pivot_df['累计总计'] = pivot_df.sum(axis=1)
            pivot_df['月均数值'] = pivot_df['累计总计'] / num_m
            pivot_df = pivot_df.sort_values(by='月均数值', ascending=False).reset_index()
            
            st.dataframe(
                pivot_df.style.background_gradient(subset=['月均数值'], cmap='YlOrRd').format(precision=2), 
                use_container_width=True
            )

            # --- 增量分析 ---
            if num_m >= 2:
                st.divider()
                st.subheader("🆕 本月新增品种检测")
                curr_m, prev_m = months[-1], months[-2]
                
                curr_df = full_df[full_df['所属月份'] == curr_m]
                prev_df = full_df[full_df['所属月份'] == prev_m]
                
                curr_set = set(curr_df['产品名称'] + " | " + curr_df['型号'])
                prev_set = set(prev_df['产品名称'] + " | " + prev_df['型号'])
                
                new_items = curr_set - prev_set
                
                if new_items:
                    st.success(f"📌 相比 {prev_m}，{curr_m} 新增了 {len(new_items)} 款产品")
                    new_df = pd.DataFrame([item.split(" | ") for item in new_items], columns=['产品名称', '型号'])
                    st.table(new_df.head(15))
                else:
                    st.info("本月无新增品种。")
        else:
            st.info("请上传有效的计划表文件。")

else:  # 新版：计划与仓库联动
    st.sidebar.subheader("📁 联动数据上传")
    plan_files = st.sidebar.file_uploader("1. 上传本期【采购计划】", accept_multiple_files=True)
    stock_file = st.sidebar.file_uploader("2. 上传当前【仓库结存】")

    if plan_files:
        plans = [load_data_new_smart(f) for f in plan_files]
        plans = [p for p in plans if p is not None]
        
        if plans:
            full_plan = pd.concat(plans, ignore_index=True)
            
            if stock_file:
                stock_df = load_data_new_smart(stock_file)
                if stock_df is not None:
                    # 合并逻辑：按产品名称和厂商进行聚合匹配
                    s_sum = stock_df.groupby(['产品名称', '生产厂商'])['仓库库存'].sum().reset_index()
                    
                    # 为了匹配更稳健，去除空格
                    full_plan['产品名称'] = full_plan['产品名称'].str.strip()
                    s_sum['产品名称'] = s_sum['产品名称'].str.strip()
                    
                    merged = pd.merge(full_plan, s_sum, on=['产品名称', '生产厂商'], how='left').fillna(0)
                    
                    # 计算建议采购量 (假设逻辑：如果库存充足则标记)
                    if '数量' in merged.columns:
                        merged['状态'] = merged.apply(lambda x: "✅ 库存充足" if x['仓库库存'] >= x['数量'] else "⚠️ 需补货", axis=1)

                    st.subheader("🔍 计划与库存智能对照表")
                    # 动态列选择
                    display_cols = ['产品名称', '型号', '生产厂商', '数量', '仓库库存']
                    if '状态' in merged.columns: display_cols.append('状态')
                    
                    st.dataframe(
                        merged[display_cols].style.applymap(
                            lambda x: 'color: red' if x == "⚠️ 需补货" else ('color: green' if x == "✅ 库存充足" else ''),
                            subset=['状态'] if '状态' in merged.columns else []
                        ), 
                        use_container_width=True
                    )
            else:
                st.subheader("📦 待分析计划预览")
                st.dataframe(full_plan, use_container_width=True)
                st.warning("💡 提示：请在左侧上传【仓库结存表】以激活库存比对功能。")

# ==========================================
# 5. 页脚
# ==========================================
st.sidebar.markdown("---")
st.sidebar.caption("💡 建议：Excel 文件请保留表头行为关键字段名。")
