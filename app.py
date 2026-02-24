import streamlit as st
import pandas as pd
import plotly.express as px

# 1. 页面配置
st.set_page_config(page_title="医疗器械采购-仓库联动分析", layout="wide")

# Win7 兼容性补丁：强制显示滚动条
st.markdown("""
    <style>
    .main .block-container { overflow-y: auto !important; }
    html, body, [data-testid="stAppViewContainer"] { overflow: visible !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏥 采购计划与仓库库存联动平台")

# --- 2. 侧边栏配置 ---
st.sidebar.header("⚙️ 配置选项")
template_type = st.sidebar.radio(
    "选择计划表模板",
    ["旧版模板 (2025总计划格式)", "新版模板 (仓库联动格式)"]
)

st.sidebar.markdown("---")
st.sidebar.header("📁 上传数据源")
plan_files = st.sidebar.file_uploader("上传【采购计划表】(支持多选 xls/xlsx/csv)", accept_multiple_files=True)
stock_file = st.sidebar.file_uploader("上传【仓库结存表】", type=['xls', 'xlsx', 'csv'])

# --- 3. 通用数据读取函数 ---
def load_data(file, skip):
    try:
        if file.name.endswith('.csv'):
            return pd.read_csv(file, skiprows=skip)
        elif file.name.endswith('.xls'):
            return pd.read_excel(file, skiprows=skip, engine='xlrd')
        else:
            return pd.read_excel(file, skiprows=skip, engine='openpyxl')
    except Exception as e:
        st.error(f"读取 {file.name} 失败，请检查 requirements.txt 是否包含 xlrd: {e}")
        return None

# --- 4. 仓库数据处理逻辑 ---
stock_summary = None
if stock_file:
    # 仓库结存表通常标题在第1或2行，这里设为自动清洗
    s_df = load_data(stock_file, skip=0) # 结存表通常第一行就是标题，如果不准可改skip=1
    if s_df is not None:
        # 字段自动映射：将您的字段名映射为程序统一字段名
        s_map = {
            '耗材名称': '产品名称',
            '结存数量': '仓库库存',
            '生产厂商': '生产厂商'
        }
        s_df.rename(columns=s_map, inplace=True)
        
        # 只要包含这三列就进行清洗
        required_cols = ['产品名称', '生产厂商', '仓库库存']
        if all(col in s_df.columns for col in required_cols):
            # 清洗：去空格、转字符串、处理重复项
            s_df['产品名称'] = s_df['产品名称'].astype(str).str.strip()
            s_df['生产厂商'] = s_df['生产厂商'].astype(str).str.strip()
            s_df['仓库库存'] = pd.to_numeric(s_df['仓库库存'], errors='coerce').fillna(0)
            
            # 汇总库存（防止同一产品有多个批次导致重复行）
            stock_summary = s_df.groupby(['产品名称', '生产厂商'])['仓库库存'].sum().reset_index()
            st.sidebar.success("✅ 仓库结存对应成功")
        else:
            st.sidebar.error("仓库表缺少必要列：耗材名称、生产厂商 或 结存数量")

# --- 5. 采购计划处理与分析 ---
if plan_files:
    plan_list = []
    for f in plan_files:
        skip_n = 3 if template_type == "旧版模板 (2025总计划格式)" else 2
        p_df = load_data(f, skip=skip_n)
        if p_df is not None:
            p_df = p_df.dropna(subset=['产品名称']).copy()
            # 统一计划表的厂商列名
            if '厂商' in p_df.columns:
                p_df.rename(columns={'厂商': '生产厂商'}, inplace=True)
            elif '生产企业（国内一级代理）' in p_df.columns:
                p_df.rename(columns={'生产企业（国内一级代理）': '生产厂商'}, inplace=True)
            
            p_df['来源月份'] = f.name.split('.')[0]
            plan_list.append(p_df)
    
    if plan_list:
        full_df = pd.concat(plan_list, ignore_index=True)
        full_df['产品名称'] = full_df['产品名称'].astype(str).str.strip()
        full_df['生产厂商'] = full_df['生产厂商'].astype(str).str.strip()
        
        # --- 联动合并 ---
        if stock_summary is not None:
            # 使用“产品名称”和“生产厂商”双重匹配
            final_df = pd.merge(full_df, stock_summary, on=['产品名称', '生产厂商'], how='left')
            final_df['仓库库存'] = final_df['仓库库存'].fillna(0)
            
            st.header("🔍 采购与仓库联动对比")
            # 标记库存充足的项目
            def highlight_stock(row):
                if row['仓库库存'] >= row['数量'] and row['数量'] > 0:
                    return ['background-color: #e6ffed'] * len(row) # 浅绿色提醒
                return [''] * len(row)

            # 展示表格
            display_cols = ['产品名称', '型号', '生产厂商', '数量', '仓库库存', '金额', '科室', '来源月份']
            # 过滤存在的列
            actual_cols = [c for c in display_cols if c in final_df.columns]
            
            st.dataframe(
                final_df[actual_cols].style.apply(highlight_stock, axis=1).format(precision=2),
                use_container_width=True
            )
            
            # 核心指标统计
            c1, c2, c3 = st.columns(3)
            c1.metric("总采购品种", f"{len(final_df)} 种")
            c2.metric("库存充足品种", f"{len(final_df[final_df['仓库库存'] >= final_df['数量']])} 种")
            c3.metric("计划采购总额", f"￥{final_df['金额'].sum():,.2f}")
        else:
            st.dataframe(full_df, use_container_width=True)
            st.warning("👈 请上传结存表以显示库存对比。")

        # --- 产品月均值分析 ---
        st.header("📈 产品历史月均采购量")
        num_months = full_df['来源月份'].nunique()
        avg_df = full_df.groupby(['产品名称', '型号', '生产厂商'])['数量'].sum().reset_index()
        avg_df['月均采购量'] = avg_df['数量'] / num_months
        avg_df = avg_df.sort_values('月均采购量', ascending=False)
        
        st.dataframe(avg_df[['产品名称', '型号', '月均采购量']].head(20), use_container_width=True)

        # 可视化
        fig = px.bar(avg_df.head(15), x='产品名称', y='月均采购量', title="重点产品月均需求排行")
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("💡 请先上传采购计划表。")
