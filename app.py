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
# 2. 核心处理函数
# ==========================================

def load_data_old(file):
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, skiprows=3)
        else:
            df = pd.read_excel(file, skiprows=3, engine=engine)
        
        df.columns = [f"{c}_{i}" if list(df.columns).count(c) > 1 else c for i, c in enumerate(df.columns)]
        df = df.dropna(subset=['产品名称'])
        # 提取文件名作为月份标识
        df['所属月份'] = file.name.split('.')[0]
        
        num_cols = ['数量', '金额', '供应医院价格（单位：元）']
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        for col in ['产品名称', '型号', '规格']:
            if col in df.columns:
                df[col] = df[col].astype(str).replace('nan', '-')
        return df
    except Exception as e:
        st.error(f"解析文件 {file.name} 失败: {e}")
        return None

def load_data_new_smart(file):
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        df_raw = pd.read_excel(file, header=None, engine=engine) if not file.name.endswith('.csv') else pd.read_csv(file, header=None)
        
        header_idx = 0
        for i, row in df_raw.head(20).iterrows():
            if any(k in str(val) for val in row.values for k in ["产品名称", "耗材名称"]):
                header_idx = i
                break
        
        df = df_raw.iloc[header_idx:].copy()
        df.columns = df.iloc[0]
        df = df[1:].reset_index(drop=True)
        
        name_map = {'耗材名称': '产品名称', '结存数量': '仓库库存', '生产厂商': '生产厂商', '厂商': '生产厂商'}
        df.rename(columns=lambda x: name_map.get(str(x).strip(), str(x).strip()), inplace=True)
        return df
    except Exception as e:
        st.error(f"智能解析文件 {file.name} 出错: {e}")
        return None

# ==========================================
# 3. 侧边栏
# ==========================================
st.sidebar.title("🛠️ 控制面板")
mode = st.sidebar.radio("选择分析模式", ["旧版：多月计划对比", "新版：计划/仓库联动"])
st.sidebar.markdown("---")

# ==========================================
# 4. 主界面逻辑
# ==========================================
st.title("🏥 医疗器械采购计划智能分析平台")

if mode == "旧版：多月计划对比":
    st.sidebar.subheader("📁 上传多月数据")
    uploaded_files = st.sidebar.file_uploader("支持批量上传", accept_multiple_files=True)

    if uploaded_files:
        all_dfs = [load_data_old(f) for f in uploaded_files]
        all_dfs = [d for d in all_dfs if d is not None]
        
        if all_dfs:
            full_df_all = pd.concat(all_dfs, ignore_index=True)
            
            # --- 新增：月份选择功能 ---
            available_months = sorted(full_df_all['所属月份'].unique())
            st.sidebar.subheader("📅 时间筛选")
            selected_months = st.sidebar.multiselect(
                "请选择要对比的月份", 
                options=available_months,
                default=available_months,
                help="您可以删除或添加想要对比的具体月份"
            )

            if not selected_months:
                st.warning("请至少选择一个月份进行分析。")
            else:
                # 过滤数据
                full_df = full_df_all[full_df_all['所属月份'].isin(selected_months)].copy()
                num_m = len(selected_months)
                target_col = st.sidebar.selectbox("分析指标", ["数量", "金额"])
                
                # --- 指标卡 ---
                st.subheader(f"📊 选中周期核心指标 ({', '.join(selected_months)})")
                c1, c2, c3 = st.columns(3)
                total_items = full_df['产品名称'].nunique()
                total_val = full_df[target_col].sum()
                
                c1.metric("总品种数", f"{total_items} 种")
                c2.metric(f"累计总{target_col}", f"{total_val:,.2f}")
                c3.metric(f"选中月均单品{target_col}", f"{(total_val / num_m / total_items):,.2f}" if total_items > 0 else 0)

                # --- 透视对比表 ---
                st.divider()
                st.subheader(f"🔍 各产品【{target_col}】月度对比明细")
                
                pivot_df = full_df.pivot_table(
                    index=['产品名称', '型号'], 
                    columns='所属月份', 
                    values=target_col, 
                    aggfunc='sum'
                ).fillna(0)
                
                # 确保列顺序按照月份选择的顺序排列
                pivot_df = pivot_df[selected_months]
                
                pivot_df['累计总计'] = pivot_df.sum(axis=1)
                pivot_df['平均数值'] = pivot_df['累计总计'] / num_m
                pivot_df = pivot_df.sort_values(by='平均数值', ascending=False).reset_index()
                
                st.dataframe(
                    pivot_df.style.background_gradient(subset=['平均数值'], cmap='YlOrRd').format(precision=2), 
                    use_container_width=True
                )

                # --- 变动分析 (仅在选择2个及以上月份时显示) ---
                if num_m >= 2:
                    st.divider()
                    st.subheader("🆕 品种增减变化 (对比所选最后两个月)")
                    # 取所选列表中的最后两个
                    m_curr, m_prev = selected_months[-1], selected_months[-2]
                    
                    curr_set = set(full_df[full_df['所属月份'] == m_curr]['产品名称'] + " | " + full_df[full_df['所属月份'] == m_curr]['型号'])
                    prev_set = set(full_df[full_df['所属月份'] == m_prev]['产品名称'] + " | " + full_df[full_df['所属月份'] == m_prev]['型号'])
                    
                    new_items = curr_set - prev_set
                    if new_items:
                        st.success(f"📌 相比 {m_prev}，{m_curr} 新增了 {len(new_items)} 款产品")
                        st.table(pd.DataFrame([i.split(" | ") for i in new_items], columns=['产品名称', '型号']).head(10))
                    else:
                        st.info(f"相比 {m_prev}，{m_curr} 无新增品种。")
        else:
            st.info("请上传有效的计划表文件。")

else: # 新版逻辑保持不变...
    st.sidebar.subheader("📁 联动数据上传")
    plan_files = st.sidebar.file_uploader("1. 上传本期【采购计划】", accept_multiple_files=True)
    stock_file = st.sidebar.file_uploader("2. 上传当前【仓库结存】")
    # ... (此处省略重复的新版代码逻辑，与上一版本一致)
    if plan_files:
        plans = [load_data_new_smart(f) for f in plan_files]
        plans = [p for p in plans if p is not None]
        if plans:
            full_plan = pd.concat(plans, ignore_index=True)
            if stock_file:
                stock_df = load_data_new_smart(stock_file)
                if stock_df is not None:
                    s_sum = stock_df.groupby(['产品名称', '生产厂商'])['仓库库存'].sum().reset_index()
                    merged = pd.merge(full_plan, s_sum, on=['产品名称', '生产厂商'], how='left').fillna(0)
                    st.subheader("🔍 计划与库存智能对照表")
                    st.dataframe(merged[['产品名称', '型号', '生产厂商', '数量', '仓库库存']], use_container_width=True)
            else:
                st.dataframe(full_plan, use_container_width=True)
