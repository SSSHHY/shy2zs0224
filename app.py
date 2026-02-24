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
    "选择模板类型",
    ["旧版模板 (2025总计划格式)", "新版模板 (仓库联动格式)"]
)

st.sidebar.markdown("---")
st.sidebar.header("📁 上传数据源")
plan_files = st.sidebar.file_uploader("上传【采购计划表】(支持多选 xls/xlsx/csv)", accept_multiple_files=True)

# 仅在新版模式下显示仓库上传
stock_file = None
if template_type == "新版模板 (仓库联动格式)":
    stock_file = st.sidebar.file_uploader("上传【仓库结存表】", type=['xls', 'xlsx', 'csv'])

# --- 3. 数据处理核心函数 ---
def load_and_clean_data(file, t_type):
    try:
        # 根据模板选择跳过的行数
        skip = 3 if t_type == "旧版模板 (2025总计划格式)" else 2
        
        # 判断文件格式并读取
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, skiprows=skip)
        elif file.name.endswith('.xls'):
            df = pd.read_excel(file, skiprows=skip, engine='xlrd')
        else:
            df = pd.read_excel(file, skiprows=skip, engine='openpyxl')
        
        # 基本清洗
        df = df.dropna(subset=['产品名称'])
        month_label = file.name.split('.')[0]
        df['所属月份'] = month_label
        
        # 列名统一化处理
        if t_type == "新版模板 (仓库联动格式)":
            # 新模板通常字段：产品名称, 型号, 厂商, 价格, 数量, 金额
            df.rename(columns={'厂商': '生产厂商'}, inplace=True)
        else:
            # 旧模板通常字段：产品名称, 型号, 生产企业（国内一级代理）
            df.rename(columns={'生产企业（国内一级代理）': '生产厂商'}, inplace=True)
        
        # 数值转换
        num_cols = ['数量', '金额', '价格', '供应医院价格（单位：元）']
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 文本清洗
        for col in ['产品名称', '型号', '生产厂商']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().replace('nan', '-')
                
        return df
    except Exception as e:
        st.error(f"解析 {file.name} 失败: {e}")
        return None

# --- 4. 执行逻辑 ---
if plan_files:
    # 加载计划表
    all_dfs = [load_and_clean_data(f, template_type) for f in plan_files]
    all_dfs = [d for d in all_dfs if d is not None]
    
    if all_dfs:
        full_df = pd.concat(all_dfs, ignore_index=True)
        available_months = sorted(full_df['所属月份'].unique())
        num_months = len(available_months)
        
        # --- 模块 A: 仓库联动 (仅新版) ---
        if template_type == "新版模板 (仓库联动格式)" and stock_file:
            st.header("📦 仓库库存与采购联动")
            # 仓库表通常跳过2行标题
            s_df = load_and_clean_data(stock_file, "新版模板 (仓库联动格式)")
            if s_df is not None:
                # 提取仓库关键列 (产品+厂商+数量)
                # 注意：假设仓库表的“数量”列代表结存
                s_summary = s_df[['产品名称', '生产厂商', '数量']].rename(columns={'数量': '仓库结存'})
                s_summary = s_summary.drop_duplicates(subset=['产品名称', '生产厂商'])
                
                # 合并到主计划表
                full_df = pd.merge(full_df, s_summary, on=['产品名称', '生产厂商'], how='left')
                full_df['仓库结存'] = full_df['仓库结存'].fillna(0)
                st.success("已成功匹配仓库结存数据！")

        # --- 模块 B: 核心指标卡 ---
        st.header(f"📊 采购概览 (共 {num_months} 个月)")
        target_col = st.sidebar.selectbox("分析目标", ["数量", "金额"])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("总品种数", f"{full_df['产品名称'].nunique()} 种")
        c2.metric(f"累计总{target_col}", f"{full_df[target_col].sum():,.0f}")
        c3.metric(f"月均单品{target_col}", f"{(full_df[target_col].sum() / num_months / full_df['产品名称'].nunique()):,.2f}")

        # --- 模块 C: 产品维度深度分析 & 均值 ---
        st.header(f"🔍 产品明细与月均值 ({target_col})")
        
        # 动态包含仓库结存列
        pivot_cols = ['产品名称', '型号', '生产厂商']
        pivot_df = full_df.pivot_table(
            index=pivot_cols, 
            columns='所属月份', 
            values=target_col, 
            aggfunc='sum'
        ).fillna(0)
        
        pivot_df['月均数值'] = pivot_df.sum(axis=1) / num_months
        pivot_df = pivot_df.sort_values(by='月均数值', ascending=False).reset_index()
        
        # 如果有仓库数据，关联显示到总表
        if '仓库结存' in full_df.columns:
            latest_stock = full_df.groupby(['产品名称', '型号', '生产厂商'])['仓库结存'].last().reset_index()
            pivot_df = pd.merge(pivot_df, latest_stock, on=['产品名称', '型号', '生产厂商'], how='left')

        st.dataframe(
            pivot_df.style.background_gradient(subset=['月均数值'], cmap='YlOrRd').format(precision=2),
            use_container_width=True
        )

        # --- 模块 D: 变动分析 (较往月) ---
        if num_months >= 2:
            st.header("🆕 采购变动分析")
            curr_m = available_months[-1]
            prev_m = available_months[-2]
            
            curr_set = set(full_df[full_df['所属月份']==curr_m]['产品名称'] + full_df[full_df['所属月份']==curr_m]['生产厂商'])
            prev_set = set(full_df[full_df['所属月份']==prev_m]['产品名称'] + full_df[full_df['所属月份']==prev_m]['生产厂商'])
            
            new_items = curr_set - prev_set
            if new_items:
                st.warning(f"相比于 {prev_m}，{curr_m} 新增了 {len(new_items)} 款产品。")
            else:
                st.info("本月无新增产品。")

        # --- 模块 E: 可视化 ---
        st.subheader(f"Top 15 产品月均{target_col}排行")
        top_15 = pivot_df.head(15)
        fig = px.bar(top_15, x='产品名称', y='月均数值', color='生产厂商', text_auto='.2s')
        st.plotly_chart(fig, use_container_width=True)

        # --- 模块 F: 智能助手 ---
        st.header("🤖 智能分析助手")
        q = st.text_input("针对数据提问：")
        if q:
            if "库存" in q and "仓库结存" in full_df.columns:
                over_stock = pivot_df[pivot_df['仓库结存'] > pivot_df['月均数值']*2].head(5)
                st.write(f"助手：发现 {len(over_stock)} 项产品库存远高于月均采购量，建议核减。")
            elif "增加" in q or "新增" in q:
                st.write("助手：请查看『采购变动分析』板块获取新增明细。")
            else:
                st.write("助手：您可以尝试询问关于‘均值’、‘库存’或‘最大金额’的问题。")
else:
    st.info("💡 请在左侧选择模板并上传 Excel 文件。")
