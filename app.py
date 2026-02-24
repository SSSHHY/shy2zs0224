import streamlit as st
import pandas as pd
import plotly.express as px

# 1. 页面配置
st.set_page_config(page_title="医疗器械采购智能分析平台", layout="wide")

# Win7 浏览器滑动兼容性补丁
st.markdown("""
    <style>
    .main .block-container { overflow-y: auto !important; }
    html, body, [data-testid="stAppViewContainer"] { overflow: visible !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏥 医疗器械采购计划智能分析平台")

# --- 2. 侧边栏配置 ---
st.sidebar.header("⚙️ 配置选项")
template_type = st.sidebar.radio(
    "选择当前的业务模式",
    ["旧版模式 (仅计划表分析)", "新版模式 (计划与仓库联动)"]
)

st.sidebar.markdown("---")
st.sidebar.header("📁 上传数据源")

# 无论哪种模式都要上传计划表
plan_files = st.sidebar.file_uploader("上传【采购计划表】(支持多选 xls/xlsx/csv)", accept_multiple_files=True)

# 【核心改动】仅在新版模式下显示结存表上传
stock_file = None
if template_type == "新版模式 (计划与仓库联动)":
    st.sidebar.info("提示：请先上传采购计划，再上传仓库结存表进行比对。")
    stock_file = st.sidebar.file_uploader("上传【仓库结存表】", type=['xls', 'xlsx', 'csv'])

# --- 3. 强化版数据读取函数 (自动找标题行) ---
def load_data_smart(file):
    try:
        # 读取原始数据
        if file.name.endswith('.csv'):
            df_raw = pd.read_csv(file, header=None)
        elif file.name.endswith('.xls'):
            df_raw = pd.read_excel(file, header=None, engine='xlrd')
        else:
            df_raw = pd.read_excel(file, header=None, engine='openpyxl')
        
        # 自动定位标题行：寻找包含“名称”关键词的行
        header_idx = 0
        found = False
        for i, row in df_raw.head(20).iterrows():
            row_values = [str(val) for val in row.values]
            if any(k in val for val in row_values for k in ["产品名称", "耗材名称", "产品名称"]):
                header_idx = i
                found = True
                break
        
        df = df_raw.iloc[header_idx:].copy()
        df.columns = df.iloc[0] # 设为标题
        df = df[1:] # 移除标题行本身
        
        # 提取月份标签
        month_label = file.name.split('.')[0]
        df['数据月份'] = month_label
        
        # 【关键修复】统一列名映射，解决 KeyError
        col_map = {
            '耗材名称': '产品名称',
            '厂商': '生产厂商',
            '生产厂家': '生产厂商',
            '生产企业（国内一级代理）': '生产厂商',
            '结存数量': '仓库结存',
            '供应医院价格（单位：元）': '价格'
        }
        # 批量重命名存在的列
        df.rename(columns=lambda x: col_map.get(str(x).strip(), str(x).strip()), inplace=True)
        
        # 清洗
        if '产品名称' in df.columns:
            df = df.dropna(subset=['产品名称'])
            df['产品名称'] = df['产品名称'].astype(str).str.strip()
        
        # 数值化
        for col in ['数量', '金额', '价格', '仓库结存']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        return df
    except Exception as e:
        st.error(f"解析文件 {file.name} 失败: {e}")
        return None

# --- 4. 执行仓库数据逻辑 ---
stock_summary = None
if stock_file:
    s_df = load_data_smart(stock_file)
    if s_df is not None:
        if '产品名称' in s_df.columns:
            # 兼容：如果结存表里叫生产厂商
            v_col = '生产厂商' if '生产厂商' in s_df.columns else s_df.columns[0]
            # 汇总（处理多批次）
            stock_summary = s_df.groupby(['产品名称', v_col])['仓库结存'].sum().reset_index()
            stock_summary.columns = ['产品名称', '生产厂商', '仓库结存']
            st.sidebar.success("✅ 仓库结存表已匹配")

# --- 5. 执行计划表分析逻辑 ---
if plan_files:
    all_dfs = [load_data_smart(f) for f in plan_files if load_data_smart(f) is not None]
    
    if all_dfs:
        full_df = pd.concat(all_dfs, ignore_index=True)
        available_months = sorted(full_df['数据月份'].unique())
        num_months = len(available_months)
        
        # 指标卡
        st.header(f"📊 采购数据概览 (共 {num_months} 个月)")
        target_col = st.sidebar.selectbox("分析目标", ["数量", "金额"])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("总品种数", f"{full_df['产品名称'].nunique()} 种")
        c2.metric(f"累计{target_col}", f"{full_df[target_col].sum():,.0f}")
        c3.metric("月均单品需求", f"{(full_df[target_col].sum() / num_months / full_df['产品名称'].nunique()):,.2f}")

        # --- 联动逻辑 ---
        if template_type == "新版模式 (计划与仓库联动)" and stock_summary is not None:
            # 联动合并
            full_df = pd.merge(full_df, stock_summary, on=['产品名称', '生产厂商'], how='left')
            full_df['仓库结存'] = full_df['仓库结存'].fillna(0)
            
            st.header("🔍 采购 vs 仓库库存 联动表")
            display_df = full_df[['产品名称', '型号', '生产厂商', '数量', '仓库结存', '数据月份']].copy()
            st.dataframe(display_df.style.background_gradient(subset=['仓库结存'], cmap='Greens'), use_container_width=True)
        else:
            # 旧版或未上传库存时，仅显示计划
            st.header("🔍 采购明细统计")
            pivot_df = full_df.pivot_table(index=['产品名称', '型号'], columns='数据月份', values=target_col, aggfunc='sum').fillna(0)
            pivot_df['月平均'] = pivot_df.sum(axis=1) / num_months
            st.dataframe(pivot_df.style.background_gradient(cmap='YlOrRd'), use_container_width=True)

        # --- 变动分析 ---
        if num_months >= 2:
            st.header("🆕 较上月新增产品")
            curr_m, prev_m = available_months[-1], available_months[-2]
            new_items = set(full_df[full_df['数据月份']==curr_m]['产品名称']) - set(full_df[full_df['数据月份']==prev_m]['产品名称'])
            if new_items:
                st.write(f"相比于 {prev_m}，本月新增了 {len(new_items)} 种产品：")
                st.info(", ".join(list(new_items)[:15]) + " 等...")
            else:
                st.write("本月无新增产品。")

        # 可视化
        st.subheader("采购趋势分析")
        fig = px.bar(full_df.groupby(['产品名称', '数据月份'])[target_col].sum().reset_index().head(20), 
                     x='产品名称', y=target_col, color='数据月份', barmode='group')
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("💡 请在左侧上传文件开始分析。旧版仅需上传计划表，新版可额外上传结存表。")
