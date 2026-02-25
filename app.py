import streamlit as st
import pandas as pd
import plotly.express as px

# 1. 页面配置与 Win7 兼容补丁
st.set_page_config(page_title="医疗器械采购智能分析平台", layout="wide")
st.markdown("""
    <style>
    .main .block-container { overflow-y: auto !important; }
    html, body, [data-testid="stAppViewContainer"] { overflow: visible !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏥 医疗器械采购计划智能分析平台")

# --- 2. 侧边栏模式选择 ---
st.sidebar.header("⚙️ 模式选择")
mode = st.sidebar.radio("请选择功能模式", ["旧版：多月计划对比分析", "新版：计划与仓库联动"])
st.sidebar.markdown("---")
st.sidebar.header("📁 上传区域")

# --- 3. 【旧版逻辑分支】完全保留原有逻辑，不作改动 ---
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
            c3.metric("月均单品需求", f"{(full_df[target_col].sum() / num_m / full_df['产品名称'].nunique()):,.2f}")

            st.header(f"🔍 各产品【{target_col}】月度对比")
            pivot_df = full_df.pivot_table(index=['产品名称', '型号'], columns='所属月份', values=target_col, aggfunc='sum').fillna(0)
            pivot_df['累计总计'] = pivot_df.sum(axis=1)
            pivot_df['月均数值'] = pivot_df['累计总计'] / num_m
            pivot_df = pivot_df.sort_values(by='月均数值', ascending=False).reset_index()
            st.dataframe(pivot_df.style.background_gradient(subset=['月均数值'], cmap='YlOrRd').format(precision=2), use_container_width=True)

# --- 4. 【新版逻辑分支】严格三键匹配 + 保留缺失为NA + 顺序保持 + 未匹配则数量金额缺失 ---
else:
    plan_files = st.sidebar.file_uploader("1. 上传【新版计划表】", accept_multiple_files=True, type=['csv', 'xlsx', 'xls'])
    stock_file = st.sidebar.file_uploader("2. 上传【仓库结存表】", type=['csv', 'xlsx', 'xls'])

    # ✅ 固定三键，不允许退化
    JOIN_KEYS = ['产品名称', '型号', '生产厂商']

    def load_new_smart(file):
        try:
            if file.name.endswith('.csv'):
                df_raw = pd.read_csv(file, header=None)
            elif file.name.endswith('.xls'):
                df_raw = pd.read_excel(file, header=None, engine='xlrd')
            else:
                df_raw = pd.read_excel(file, header=None, engine='openpyxl')

            # 智能找标题
            header_idx = 0
            for i, row in df_raw.head(20).iterrows():
                row_vals = [str(v) for v in row.values]
                if any(k in v for v in row_vals for k in ["产品名称", "耗材名称"]):
                    header_idx = i
                    break

            df = df_raw.iloc[header_idx:].copy()
            df.columns = df.iloc[0]
            df = df[1:].copy()

            # 字段映射（你要求的对应）
            name_map = {
                '耗材名称': '产品名称',
                '产品名称': '产品名称',
                '规格': '型号',
                '型号': '型号',
                '厂商': '生产厂商',
                '生产厂家': '生产厂商',
                '生产厂商': '生产厂商',
                '结存数量': '仓库库存',
                '仓库库存': '仓库库存',
            }
            df.rename(columns=lambda x: name_map.get(str(x).strip(), str(x).strip()), inplace=True)

            # ✅ 确保三键列一定存在（缺就补 NA）
            for k in JOIN_KEYS:
                if k not in df.columns:
                    df[k] = pd.NA

            # ✅ 关键：文本列用 pandas string dtype，保留 NA，不要变成 ''
            for col in JOIN_KEYS:
                df[col] = df[col].astype("string").str.strip()

                # 把常见“伪缺失”统一成 NA（注意：这里不要转成空字符串）
                df[col] = df[col].replace(
                    to_replace=[pd.NA, "nan", "None", "-", "", " "],
                    value=pd.NA
                )

            # 数值列（允许缺失）
            for col in ['数量', '金额', '价格', '仓库库存']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            return df

        except Exception as e:
            st.error(f"读取失败 ({file.name}): {e}")
            return None

    if plan_files:
        plans = [load_new_smart(f) for f in plan_files if load_new_smart(f) is not None]
        if plans:
            # 合并计划表 + 顺序锚点
            full_plan_raw = pd.concat(plans, ignore_index=True)
            full_plan_raw['_order'] = range(len(full_plan_raw))

            # 计划汇总：同物料多行相加，并保留第一次出现顺序
            order_df = full_plan_raw.groupby(JOIN_KEYS, as_index=False, dropna=False)['_order'].min()

            agg_dict = {}
            if '数量' in full_plan_raw.columns:
                agg_dict['数量'] = 'sum'
            if '金额' in full_plan_raw.columns:
                agg_dict['金额'] = 'sum'

            full_plan = full_plan_raw.groupby(JOIN_KEYS, as_index=False, dropna=False).agg(agg_dict)
            full_plan = pd.merge(full_plan, order_df, on=JOIN_KEYS, how='left').sort_values('_order')

            if stock_file:
                stock_df = load_new_smart(stock_file)
                if stock_df is None or '仓库库存' not in stock_df.columns:
                    st.error("结存表解析失败或缺少库存字段（结存数量/仓库库存）。")
                else:
                    # 结存汇总（同物料相加），dropna=False 让缺规格的行也保留，但它不会匹配到有规格的计划行
                    s_sum = stock_df.groupby(JOIN_KEYS, as_index=False, dropna=False)['仓库库存'].sum()

                    # 左连接：严格三键
                    merged = pd.merge(full_plan, s_sum, on=JOIN_KEYS, how='left').sort_values('_order')

                    # ✅ 只要库存缺失（说明三键没匹配到，包括“规格缺失导致不匹配”）→ 数量金额标缺失
                    mask_no_stock = merged['仓库库存'].isna()
                    for col in ['数量', '金额']:
                        if col in merged.columns:
                            merged.loc[mask_no_stock, col] = pd.NA

                    merged_show = merged.drop(columns=['_order'])

                    st.header("🔍 计划与库存联动清单 (匹配规则：名称+型号+厂商，缺任一键=不匹配)")
                    st.dataframe(
                        merged_show.style.format(precision=0, na_rep="缺失"),
                        use_container_width=True
                    )
            else:
                st.dataframe(full_plan.drop(columns=['_order']), use_container_width=True)
