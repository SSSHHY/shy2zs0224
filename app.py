import streamlit as st
import pandas as pd
import plotly.express as px
import re

# 1. 页面配置与 Win7 兼容性补丁
st.set_page_config(page_title="医疗器械采购智能分析平台", layout="wide")
st.markdown("""
    <style>
    .main .block-container { overflow-y: auto !important; }
    html, body, [data-testid="stAppViewContainer"] { overflow: visible !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏥 医疗器械采购计划智能分析平台")

# --- 辅助工具函数 ---
def clean_numeric(value):
    """清洗数值：处理科学计数法、字符串格式及异常值"""
    if pd.isna(value) or str(value).strip() == "":
        return 0.0
    try:
        # 处理可能的科学计数法或带逗号的字符串
        num = float(str(value).replace(',', '').strip())
        return num
    except:
        return 0.0

# --- 2. 侧边栏：模式选择 ---
st.sidebar.header("⚙️ 模式选择")
mode = st.sidebar.radio(
    "请选择功能模式",
    ["旧版：多月计划对比分析", "新版：计划与仓库联动"]
)

st.sidebar.markdown("---")
st.sidebar.header("📁 上传区域")

# --- 3. 逻辑分离：旧版模式 (保持不动) ---
if mode == "旧版：多月计划对比分析":
    uploaded_files = st.sidebar.file_uploader("点击上传多个月份计划表", accept_multiple_files=True, type=['csv', 'xlsx', 'xls'])

    def load_old_version(file):
        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file, skiprows=3)
            elif file.name.endswith('.xls'):
                df = pd.read_excel(file, skiprows=3, engine='xlrd')
            else:
                df = pd.read_excel(file, skiprows=3, engine='openpyxl')
            
            df.columns = [f"{c}_{i}" if list(df.columns).count(c) > 1 else c for i, c in enumerate(df.columns)]
            df = df.dropna(subset=['产品名称'])
            df['所属月份'] = file.name.split('.')[0]
            
            for col in ['数量', '金额', '供应医院价格（单位：元）']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
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
            
            c1, c2, c3 = st.columns(3)
            c1.metric("总品种数", f"{full_df['产品名称'].nunique()} 种")
            c2.metric(f"累计{target_col}", f"{full_df[target_col].sum():,.0f}")
            c3.metric(f"月均单品{target_col}", f"{(full_df[target_col].sum() / num_m / full_df['产品名称'].nunique()):,.2f}")

            st.header(f"🔍 各产品【{target_col}】月度对比")
            pivot_df = full_df.pivot_table(index=['产品名称', '型号'], columns='所属月份', values=target_col, aggfunc='sum').fillna(0)
            pivot_df['累计总计'] = pivot_df.sum(axis=1)
            pivot_df['月均数值'] = pivot_df['累计总计'] / num_m
            pivot_df = pivot_df.sort_values(by='月均数值', ascending=False).reset_index()
            st.dataframe(pivot_df.style.background_gradient(subset=['月均数值'], cmap='YlOrRd').format(precision=2), use_container_width=True)

            if num_m >= 2:
                st.header("🆕 较往月新增产品")
                curr, prev = months[-1], months[-2]
                curr_set = set(full_df[full_df['所属月份']==curr]['产品名称'] + " | " + full_df[full_df['所属月份']==curr]['型号'])
                prev_set = set(full_df[full_df['所属月份']==prev]['产品名称'] + " | " + full_df[full_df['所属月份']==prev]['型号'])
                new_keys = curr_set - prev_set
                if new_keys:
                    st.success(f"📌 相比 {prev}，本月新增 {len(new_keys)} 款产品")
                    st.table(pd.DataFrame([k.split(" | ") for k in new_keys], columns=['产品名称', '型号']).head(10))

# --- 4. 逻辑分离：新版模式 (需求修改部分) ---
else:
    plan_files = st.sidebar.file_uploader("1. 上传【新版计划表】", accept_multiple_files=True)
    stock_file = st.sidebar.file_uploader("2. 上传【仓库结存表】")

    def load_new_smart(file):
        try:
            engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
            df_raw = pd.read_excel(file, header=None, engine=engine) if not file.name.endswith('.csv') else pd.read_csv(file, header=None)
            
            # 自动找标题行
            header_idx = 0
            for i, row in df_raw.head(20).iterrows():
                row_vals = [str(val) for val in row.values]
                if any(k in "".join(row_vals) for k in ["产品名称", "耗材名称", "型号", "规格", "结存"]):
                    header_idx = i
                    break
            
            df = df_raw.iloc[header_idx:].copy()
            df.columns = df.iloc[0]
            df = df[1:].reset_index(drop=True)
            
            # 清洗列名：去除空格和换行
            df.columns = [str(c).strip().replace('\n', '') for c in df.columns]
            
            # 统一字段名映射 (核心需求1)
            name_map = {
                '耗材名称': '产品名称', 
                '结存数量': '仓库库存', 
                '结存': '仓库库存',
                '厂商': '生产厂商',
                '规格': '型号'  # 将规格统一映射到型号，方便对齐
            }
            df.rename(columns=name_map, inplace=True)
            
            # 数值清洗 (核心需求2)
            if '仓库库存' in df.columns:
                df['仓库库存'] = df['仓库库存'].apply(clean_numeric)
            if '数量' in df.columns:
                df['数量'] = df['数量'].apply(clean_numeric)
            
            # 文本清洗：去除空值导致的 nan 字符串
            for col in ['产品名称', '型号', '生产厂商']:
                if col in df.columns:
                    df[col] = df[col].astype(str).replace(['nan', 'None', 'None'], '-')
            
            return df
        except Exception as e:
            st.error(f"解析文件 {file.name} 出错: {e}")
            return None

    if plan_files:
        plans = [load_new_smart(f) for f in plan_files if load_new_smart(f) is not None]
        if plans:
            full_plan = pd.concat(plans, ignore_index=True)
            
            if stock_file:
                stock_df = load_new_smart(stock_file)
                if stock_df is not None:
                    # 按照 产品名称+型号+生产厂商 进行聚合，防止仓库表有重复项
                    # 如果仓库表没有型号或厂商，会自动填充'-'进行对齐
                    group_cols = []
                    for c in ['产品名称', '型号', '生产厂商']:
                        if c in stock_df.columns: group_cols.append(c)
                    
                    s_sum = stock_df.groupby(group_cols)['仓库库存'].sum().reset_index()
                    
                    # 合并对比 (核心需求1：三维度对齐)
                    merge_keys = [k for k in group_cols if k in full_plan.columns]
                    merged = pd.merge(full_plan, s_sum, on=merge_keys, how='left').fillna(0)
                    
                    st.header("🔍 计划与库存联动清单")
                    # 动态显示列
                    display_cols = ['产品名称', '型号', '生产厂商', '数量', '仓库库存']
                    # 过滤掉不存在的列避免报错
                    actual_display = [c for c in display_cols if c in merged.columns]
                    
                    st.dataframe(
                        merged[actual_display].style.format({'数量': '{:,.0f}', '仓库库存': '{:,.0f}'}), 
                        use_container_width=True
                    )
            else:
                st.info("💡 已加载计划表，请继续上传【仓库结存表】以完成联动分析。")
                st.dataframe(full_plan, use_container_width=True)
