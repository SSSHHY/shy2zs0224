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
    "选择上传的计划表模板",
    ["旧版模板 (2025总计划格式)", "新版模板 (仓库联动格式)"]
)

st.sidebar.markdown("---")
st.sidebar.header("📁 上传数据源")
# 计划表上传
plan_files = st.sidebar.file_uploader("点击上传多个月份计划表", accept_multiple_files=True, type=['csv', 'xlsx', 'xls'])

# 仓库结存上传（仅在新版模式下或需要对比时使用）
stock_file = st.sidebar.file_uploader("上传【仓库结存表】(可选)", type=['xls', 'xlsx', 'csv'])

# --- 3. 核心数据读取函数 ---
def load_data_smart(file, t_type):
    try:
        # 判断文件格式
        if file.name.endswith('.csv'):
            df_raw = pd.read_csv(file, header=None)
        elif file.name.endswith('.xls'):
            df_raw = pd.read_excel(file, header=None, engine='xlrd')
        else:
            df_raw = pd.read_excel(file, header=None, engine='openpyxl')
        
        # 智能寻找标题行逻辑
        header_idx = 0
        found = False
        # 扫描前20行寻找关键词
        for i, row in df_raw.head(20).iterrows():
            row_values = [str(val) for val in row.values]
            if any("产品名称" in val or "耗材名称" in val for val in row_values):
                header_idx = i
                found = True
                break
        
        # 如果没搜到，则按照用户代码中的固定跳过行数
        if not found:
            header_idx = 3 if t_type == "旧版模板 (2025总计划格式)" else 2
            
        df = df_raw.iloc[header_idx:].copy()
        df.columns = df.iloc[0] # 设为标题
        df = df[1:] # 移除标题行本身
        
        # 基础清洗
        df = df.dropna(subset=['产品名称'])
        month_label = file.name.split('.')[0]
        df['所属月份'] = month_label
        
        # 统一不同模板的列名
        name_map = {
            '生产企业（国内一级代理）': '生产厂商',
            '厂商': '生产厂商',
            '耗材名称': '产品名称',
            '供应医院价格（单位：元）': '价格',
            '结存数量': '仓库库存'
        }
        df.rename(columns=name_map, inplace=True)
        
        # 数值转换
        num_cols = ['数量', '金额', '价格', '仓库库存']
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 文本转换防止报错
        for col in ['产品名称', '型号', '规格', '生产厂商']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().replace('nan', '-')
                
        return df
    except Exception as e:
        st.error(f"解析文件 {file.name} 失败: {e}")
        return None

# --- 4. 处理仓库库存数据 ---
stock_summary = None
if stock_file:
    s_df = load_data_smart(stock_file, template_type)
    if s_df is not None:
        # 确保包含匹配必须的列
        if '产品名称' in s_df.columns:
            # 兼容您的结存表字段：生产厂商
            vendor_col = '生产厂商' if '生产厂商' in s_df.columns else s_df.columns[0]
            # 汇总库存（处理多批次情况）
            stock_summary = s_df.groupby(['产品名称', vendor_col])['仓库库存'].sum().reset_index()
            stock_summary.columns = ['产品名称', '生产厂商', '仓库库存']
            st.sidebar.success("✅ 仓库结存表对应成功")

# --- 5. 计划表逻辑开始 ---
if plan_files:
    all_dfs = [load_data_smart(f, template_type) for f in plan_files if load_data_smart(f, template_type) is not None]
    
    if all_dfs:
        full_df = pd.concat(all_dfs, ignore_index=True)
        available_months = sorted(full_df['所属月份'].unique())
        num_months = len(available_months)
        
        # --- 核心指标卡 ---
        st.header(f"📊 采购概览 (共 {num_months} 个月数据)")
        target_col = st.sidebar.selectbox("分析目标", ["数量", "金额"])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("总品种数", f"{full_df['产品名称'].nunique()} 种")
        c2.metric(f"累计总{target_col}", f"{full_df[target_col].sum():,.0f}")
        c3.metric(f"月均单品{target_col}", f"{(full_df[target_col].sum() / num_months / full_df['产品名称'].nunique()):,.2f}")

        # --- 联动仓库库存 (如果上传了) ---
        if stock_summary is not None:
            full_df = pd.merge(full_df, stock_summary, on=['产品名称', '生产厂商'], how='left')
            full_df['仓库库存'] = full_df['仓库库存'].fillna(0)

        # --- 产品维度分析 & 均值 ---
        st.header(f"🔍 各产品【{target_col}】对比与月均值")
        
        pivot_idx = ['产品名称', '型号', '生产厂商']
        # 过滤掉不存在的列名
        actual_idx = [c for c in pivot_idx if c in full_df.columns]
        
        pivot_df = full_df.pivot_table(
            index=actual_idx, 
            columns='所属月份', 
            values=target_col, 
            aggfunc='sum'
        ).fillna(0)
        
        pivot_df['累计总计'] = pivot_df.sum(axis=1)
        pivot_df['月均数值'] = pivot_df['累计总计'] / num_months
        pivot_df = pivot_df.sort_values(by='月均数值', ascending=False).reset_index()
        
        # 如果有库存数据，拼接到展示表中
        if '仓库库存' in full_df.columns:
            latest_stock = full_df.groupby(actual_idx)['仓库库存'].last().reset_index()
            pivot_df = pd.merge(pivot_df, latest_stock, on=actual_idx, how='left')

        st.dataframe(
            pivot_df.style.background_gradient(subset=['月均数值'], cmap='YlOrRd').format(precision=2),
            use_container_width=True
        )

        # --- 🆕 采购变动分析 (较往月) ---
        if num_months >= 2:
            st.header("🆕 采购变动分析 (较往月)")
            col_m1, col_m2 = st.columns(2)
            curr_m = col_m1.selectbox("选择当前月", available_months, index=num_months-1)
            prev_m = col_m2.selectbox("选择对比月", available_months, index=num_months-2)
            
            curr_data = full_df[full_df['所属月份'] == curr_m]
            prev_data = full_df[full_df['所属月份'] == prev_m]
            
            curr_set = set(curr_data['产品名称'] + " | " + curr_data['型号'])
            prev_set = set(prev_data['产品名称'] + " | " + prev_data['型号'])
            
            new_keys = curr_set - prev_set
            if new_keys:
                st.success(f"📌 相比于 {prev_m}，{curr_m} 新增了 {len(new_keys)} 款产品：")
                new_list = []
                for k in new_keys:
                    name, model = k.split(" | ")
                    row = curr_data[(curr_data['产品名称']==name) & (curr_data['型号']==model)].iloc[0]
                    new_list.append({"产品名称": name, "型号": model, "数量": row['数量'], "备注": row.get('备注', '-')})
                st.table(pd.DataFrame(new_list))
            else:
                st.info("该月没有新增品种。")

        # --- 可视化 ---
        st.subheader(f"Top 15 产品月均{target_col}排行")
        top_15 = pivot_df.head(15)
        fig = px.bar(top_15, x='产品名称', y='月均数值', color='生产厂商', text_auto='.2s')
        st.plotly_chart(fig, use_container_width=True)

        # --- 智能助手 ---
        st.header("🤖 采购智能助手")
        q = st.text_input("您可以提问，例如：'新增了哪些东西？' 或 '哪些库存充足？'")
        if q:
            if "新增" in q or "增加" in q:
                st.write("助手：请查看下方的『采购变动分析』板块。")
            elif "库存" in q and '仓库库存' in pivot_df.columns:
                safe_items = pivot_df[pivot_df['仓库库存'] >= pivot_df['月均数值']]['产品名称'].tolist()
                st.write(f"助手：发现 {len(safe_items)} 项产品库存充足。")
            elif "平均" in q or "均值" in q:
                st.info(f"助手：当前月均{target_col}最高的产品是 **{pivot_df.iloc[0]['产品名称']}**。")
            else:
                st.write("助手：我可以帮您分析新增、均值和库存情况。")
else:
    st.info("💡 请在左侧选择模板类型并上传采购计划文件开始分析。")
