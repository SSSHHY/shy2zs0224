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
mode = st.sidebar.radio(
    "请选择功能模式",
    ["旧版：多月计划对比分析", "新版：计划与仓库联动"]
)
st.sidebar.markdown("---")
st.sidebar.header("📁 上传区域")

# =========================
# 旧版：多月计划对比分析（完全原封不动）
# =========================
if mode == "旧版：多月计划对比分析":
    uploaded_files = st.sidebar.file_uploader(
        "点击上传多个月份计划表",
        accept_multiple_files=True,
        type=['csv', 'xlsx', 'xls']
    )

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

            # 提取文件名作为月份标识
            df['所属月份'] = file.name.split('.')[0]

            # 数值转换
            for col in ['数量', '金额', '供应医院价格（单位：元）']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            # 文本清洗（避免报错）
            for col in ['产品名称', '型号', '规格']:
                if col in df.columns:
                    df[col] = df[col].astype(str).replace('nan', '-')

            return df
        except Exception as e:
            st.error(f"解析文件 {file.name} 失败: {e}")
            return None

    if uploaded_files:
        all_dfs = [load_old_version(f) for f in uploaded_files if load_old_version(f) is not None]

        if all_dfs:
            full_df = pd.concat(all_dfs, ignore_index=True)

            # 获取唯一月份并排序
            available_months = sorted(full_df['所属月份'].unique())
            num_months = len(available_months)

            # --- 2. 核心指标卡 ---
            st.header(f"📊 采购概览 (共 {num_months} 个月数据)")
            target_col = st.sidebar.selectbox("分析目标", ["数量", "金额"])

            c1, c2, c3 = st.columns(3)
            c1.metric("总品种数", f"{full_df['产品名称'].nunique()} 种")
            c2.metric(f"累计总{target_col}", f"{full_df[target_col].sum():,.0f}")
            c3.metric(f"月均单品{target_col}", f"{(full_df[target_col].sum() / num_months / full_df['产品名称'].nunique()):,.2f}")

            # --- 3. 产品维度深度分析 ---
            st.header(f"🔍 各产品【{target_col}】对比与月均值")

            pivot_df = full_df.pivot_table(
                index=['产品名称', '型号'],
                columns='所属月份',
                values=target_col,
                aggfunc='sum'
            ).fillna(0)

            pivot_df['累计总计'] = pivot_df.sum(axis=1)
            pivot_df['月均数值'] = pivot_df['累计总计'] / num_months
            pivot_df = pivot_df.sort_values(by='月均数值', ascending=False).reset_index()

            st.dataframe(
                pivot_df.style.background_gradient(subset=['月均数值'], cmap='YlOrRd').format(precision=2),
                use_container_width=True
            )

            # --- 4. 🆕 采购变动分析 (新增模块) ---
            st.header("🆕 采购变动分析 (较往月)")

            if num_months >= 2:
                col_m1, col_m2 = st.columns(2)
                curr_m = col_m1.selectbox("选择当前月", available_months, index=num_months - 1)
                prev_m = col_m2.selectbox("选择对比月", available_months, index=num_months - 2)

                curr_data = full_df[full_df['所属月份'] == curr_m]
                prev_data = full_df[full_df['所属月份'] == prev_m]

                # 以“产品名称 + 型号”作为唯一标识
                curr_set = set(curr_data['产品名称'].astype(str) + " | " + curr_data['型号'].astype(str))
                prev_set = set(prev_data['产品名称'].astype(str) + " | " + prev_data['型号'].astype(str))

                new_items_keys = curr_set - prev_set

                if new_items_keys:
                    st.success(f"📌 相比于 {prev_m}，{curr_m} **新增**了 {len(new_items_keys)} 款产品：")

                    new_items_list = []
                    for item in new_items_keys:
                        name, model = item.split(" | ")

                        # 防止多行：取数量之和、金额之和；其他字段取第一条
                        detail_rows = curr_data[(curr_data['产品名称'].astype(str) == name) & (curr_data['型号'].astype(str) == model)]
                        qty = detail_rows['数量'].sum() if '数量' in detail_rows.columns else 0
                        price = detail_rows['供应医院价格（单位：元）'].iloc[0] if '供应医院价格（单位：元）' in detail_rows.columns and len(detail_rows) > 0 else None
                        remark = detail_rows['备注'].iloc[0] if '备注' in detail_rows.columns and len(detail_rows) > 0 else None

                        new_items_list.append({
                            "产品名称": name,
                            "型号": model,
                            "当前月数量": qty,
                            "单价": price,
                            "备注": remark
                        })

                    st.table(pd.DataFrame(new_items_list))
                else:
                    st.info(f"✅ {curr_m} 相对 {prev_m} 没有新增品种。")
            else:
                st.warning("⚠️ 请至少上传两个月份的表格来分析新增变动。")

            # --- 5. 可视化 ---
            st.subheader(f"Top 15 产品月均{target_col}排行")
            top_15 = pivot_df.head(15)
            fig = px.bar(
                top_15,
                x='产品名称',
                y='月均数值',
                color='型号',
                text_auto='.2s',
                title="重点产品平均月采购量"
            )
            st.plotly_chart(fig, use_container_width=True)

            # --- 6. 智能助手 ---
            st.header("🤖 采购智能助手")
            q = st.text_input("您可以提问，例如：'新增了哪些东西？'")

            if q:
                if ("新增" in q) or ("增加" in q):
                    st.write("助手：请查看上方的『采购变动分析』板块，已为您列出本月新采购的明细表。")
                elif ("平均" in q) or ("均值" in q):
                    if len(pivot_df) > 0:
                        top_item = pivot_df.iloc[0]
                        st.info(f"根据数据分析，**{top_item['产品名称']}** 的月均{target_col}最高，平均每月 **{top_item['月均数值']:.2f}**。")
                    else:
                        st.info("当前数据不足以计算月均最高项。")
                else:
                    st.write("助手：您可以尝试询问关于‘新增’、‘月均最高’、‘总额’等问题。")
        else:
            st.info("💡 请在左侧上传至少两个月份的采购计划表，系统将自动计算跨月平均值及新增变动。")
    else:
        st.info("💡 请在左侧上传至少两个月份的采购计划表，系统将自动计算跨月平均值及新增变动。")

# =========================
# 新版：计划与仓库联动（已修改：计划表原样输出，不进行合并）
# =========================
else:
    plan_files = st.sidebar.file_uploader("1. 上传【新版计划表】", accept_multiple_files=True, type=['csv', 'xlsx', 'xls'])
    stock_file = st.sidebar.file_uploader("2. 上传【仓库结存表】", type=['csv', 'xlsx', 'xls'])

    JOIN_KEYS = ['产品名称', '型号', '生产厂商']

    def load_new_smart(file):
        try:
            if file.name.endswith('.csv'):
                df_raw = pd.read_csv(file, header=None)
            elif file.name.endswith('.xls'):
                df_raw = pd.read_excel(file, header=None, engine='xlrd')
            else:
                df_raw = pd.read_excel(file, header=None, engine='openpyxl')

            header_idx = 0
            for i, row in df_raw.head(20).iterrows():
                row_vals = [str(v) for v in row.values]
                if any(k in v for v in row_vals for k in ["产品名称", "耗材名称"]):
                    header_idx = i
                    break

            df = df_raw.iloc[header_idx:].copy()
            df.columns = df.iloc[0]
            df = df[1:].copy()

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

            for k in JOIN_KEYS:
                if k not in df.columns:
                    df[k] = pd.NA

            for col in JOIN_KEYS:
                df[col] = df[col].astype("string").str.strip()
                df[col] = df[col].replace(
                    to_replace=[pd.NA, "nan", "None", "-", "", " "],
                    value=pd.NA
                )

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
            # 1. 这里直接合并所有计划表，不再做 groupby 汇总处理
            full_plan = pd.concat(plans, ignore_index=True)
            
            # 记录原始顺序，保证左连接匹配后顺序不乱
            full_plan['_order'] = range(len(full_plan))

            if stock_file:
                stock_df = load_new_smart(stock_file)
                if stock_df is None or '仓库库存' not in stock_df.columns:
                    st.error("结存表解析失败或缺少库存字段（结存数量/仓库库存）。")
                else:
                    # 2. 仓库结存表依然需要汇总（因为仓库里同款产品的总库存是固定的）
                    s_sum = stock_df.groupby(JOIN_KEYS, as_index=False, dropna=False)['仓库库存'].sum()

                    # 3. 将汇总后的库存，通过左连接匹配到【原汁原味】的计划表上
                    merged = pd.merge(full_plan, s_sum, on=JOIN_KEYS, how='left').sort_values('_order')

                    # 移除用于排序的辅助列
                    merged_show = merged.drop(columns=['_order'])

                    st.header("🔍 计划与库存联动清单 ")
                    st.dataframe(
                        merged_show.style.format(precision=0, na_rep="缺失"),
                        use_container_width=True
                    )
            else:
                # 如果没有上传库存表，也直接展示原汁原味的计划表
                st.dataframe(full_plan.drop(columns=['_order']), use_container_width=True)
    else:
        st.info("💡 请在左侧上传计划表与结存表以进行联动分析。")
