import streamlit as st
import pandas as pd
import plotly.express as px

# 1. 页面配置与 Win7 补丁
st.set_page_config(page_title="医疗器械采购智能分析平台", layout="wide")
st.markdown("""
    <style>
    .main .block-container { overflow-y: auto !important; }
    html, body, [data-testid="stAppViewContainer"] { overflow: visible !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏥 医疗器械采购计划智能分析平台")

# --- 2. 侧边栏：完全独立的模式选择 ---
st.sidebar.header("⚙️ 模式选择")
mode = st.sidebar.radio(
    "请选择功能模式",
    ["旧版：多月计划对比分析", "新版：计划与仓库联动"]
)

st.sidebar.markdown("---")
st.sidebar.header("📁 上传区域")

# --- 3. 逻辑分离：旧版模式 ---
if mode == "旧版：多月计划对比分析":
    uploaded_files = st.sidebar.file_uploader("点击上传多个月份计划表", accept_multiple_files=True, type=['csv', 'xlsx', 'xls'])

    # 这里的函数完全保留您之前运行最稳的版本
    def load_old_version(file):
        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file, skiprows=3)
            elif file.name.endswith('.xls'):
                df = pd.read_excel(file, skiprows=3, engine='xlrd')
            else:
                df = pd.read_excel(file, skiprows=3, engine='openpyxl')
            
            # 解决重复列名导致的 InvalidIndexError
            df.columns = [f"{c}_{i}" if list(df.columns).count(c) > 1 else c for i, c in enumerate(df.columns)]
            
            df = df.dropna(subset=['产品名称'])
            df['所属月份'] = file.name.split('.')[0]
            
            # 数值转换
            for col in ['数量', '金额', '供应医院价格（单位：元）']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            # 文本清洗
            for col in ['产品名称', '型号', '规格']:
                if col in df.columns:
                    df[col] = df[col].astype(str).replace('nan', '-')
            return df
        except Exception as e:
            st.error(f"旧版解析失败: {e}")
            return None

    if uploaded_files:
        all_dfs = [load_old_version(f) for f in uploaded_files if load_old_version(f) is not None]
        if all_dfs:
            full_df = pd.concat(all_dfs, ignore_index=True)
            months = sorted(full_df['所属月份'].unique())
            num_m = len(months)
            
            target_col = st.sidebar.selectbox("分析目标", ["数量", "金额"])
            
            # 核心指标卡
            c1, c2, c3 = st.columns(3)
            c1.metric("总品种数", f"{full_df['产品名称'].nunique()} 种")
            c2.metric(f"累计{target_col}", f"{full_df[target_col].sum():,.0f}")
            c3.metric(f"月均单品{target_col}", f"{(full_df[target_col].sum() / num_m / full_df['产品名称'].nunique()):,.2f}")

            # 透视对比表
            st.header(f"🔍 各产品【{target_col}】月度对比")
            pivot_df = full_df.pivot_table(index=['产品名称', '型号'], columns='所属月份', values=target_col, aggfunc='sum').fillna(0)
            pivot_df['累计总计'] = pivot_df.sum(axis=1)
            pivot_df['月均数值'] = pivot_df['累计总计'] / num_m
            pivot_df = pivot_df.sort_values(by='月均数值', ascending=False).reset_index()
            st.dataframe(pivot_df.style.background_gradient(subset=['月均数值'], cmap='YlOrRd').format(precision=2), use_container_width=True)

            # 变动分析
            if num_m >= 2:
                st.header("🆕 较往月新增产品")
                curr, prev = months[-1], months[-2]
                curr_set = set(full_df[full_df['所属月份']==curr]['产品名称'] + " | " + full_df[full_df['所属月份']==curr]['型号'])
                prev_set = set(full_df[full_df['所属月份']==prev]['产品名称'] + " | " + full_df[full_df['所属月份']==prev]['型号'])
                new_keys = curr_set - prev_set
                if new_keys:
                    st.success(f"📌 相比 {prev}，本月新增 {len(new_keys)} 款产品")
                    st.table(pd.DataFrame([k.split(" | ") for k in new_keys], columns=['产品名称', '型号']).head(10))

# --- 4. 逻辑分离：新版模式 ---
else:
    plan_files = st.sidebar.file_uploader("1. 上传【新版计划表】", accept_multiple_files=True)
    stock_file = st.sidebar.file_uploader("2. 上传【仓库结存表】")

    # 新版专用的智能识别读取函数（不影响旧版）
    def load_new_smart(file):
        try:
            engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
            df_raw = pd.read_excel(file, header=None, engine=engine) if not file.name.endswith('.csv') else pd.read_csv(file, header=None)
            
            # 自动找标题
            header_idx = 0
            for i, row in df_raw.head(20).iterrows():
                if any(k in str(val) for val in row.values for k in ["产品名称", "耗材名称"]):
                    header_idx = i
                    break
            df = df_raw.iloc[header_idx:].copy()
            df.columns = df.iloc[0]
            df = df[1:].dropna(subset=[df.columns[1]]) # 假设第二列是有意义的
            
            # 统一字段名
            name_map = {'耗材名称': '产品名称', '结存数量': '仓库库存', '生产厂商': '生产厂商', '厂商': '生产厂商'}
            df.rename(columns=lambda x: name_map.get(str(x).strip(), str(x).strip()), inplace=True)
            return df
        except Exception as e:
            st.error(f"新版读取出错: {e}")
            return None

    if plan_files:
        plans = [load_new_smart(f) for f in plan_files if load_new_smart(f) is not None]
        if plans:
            full_plan = pd.concat(plans, ignore_index=True)
            
            if stock_file:
                stock_df = load_new_smart(stock_file)
                if stock_df is not None:
                    # 合并对比
                    s_sum = stock_df.groupby(['产品名称', '生产厂商'])['仓库库存'].sum().reset_index()
                    merged = pd.merge(full_plan, s_sum, on=['产品名称', '生产厂商'], how='left').fillna(0)
                    
                    st.header("🔍 计划与库存联动清单")
                    st.dataframe(merged[['产品名称', '型号', '生产厂商', '数量', '仓库库存']], use_container_width=True)
            else:
                st.dataframe(full_plan, use_container_width=True)
                st.warning("请上传结存表以开启联动。")
