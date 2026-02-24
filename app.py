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
st.sidebar.header("⚙️ 模式切换")
template_type = st.sidebar.radio(
    "选择模板模式",
    ["旧版模式 (2025总计划格式)", "新版模式 (计划与仓库联动)"]
)

st.sidebar.markdown("---")
st.sidebar.header("📁 数据上传")

# 计划表上传
plan_files = st.sidebar.file_uploader("上传【采购计划表】(支持多选)", accept_multiple_files=True, type=['csv', 'xlsx', 'xls'])

# 仅在新版模式显示仓库结存上传
stock_file = None
if template_type == "新版模式 (计划与仓库联动)":
    st.sidebar.info("💡 请先上传计划，再上传结存表对比")
    stock_file = st.sidebar.file_uploader("上传【仓库结存表】", type=['xls', 'xlsx', 'csv'])

# --- 3. 增强版读取函数 (解决重复列名报错) ---
def load_and_clean_universal(file, mode):
    try:
        # 设置跳行逻辑
        skip = 3 if mode == "旧版模式 (2025总计划格式)" else 2
        
        # 读取文件
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, skiprows=skip)
        elif file.name.endswith('.xls'):
            df = pd.read_excel(file, skiprows=skip, engine='xlrd')
        else:
            df = pd.read_excel(file, skiprows=skip, engine='openpyxl')
        
        # 【核心修复】处理重复列名，防止 concat 报错
        if not df.columns.is_unique:
            new_cols = []
            counts = {}
            for col in df.columns:
                col_str = str(col)
                if col_str in counts:
                    counts[col_str] += 1
                    new_cols.append(f"{col_str}_{counts[col_str]}")
                else:
                    counts[col_str] = 0
                    new_cols.append(col_str)
            df.columns = new_cols

        # 过滤空行
        if '产品名称' in df.columns:
            df = df.dropna(subset=['产品名称'])
        else:
            # 兼容性：如果找不到“产品名称”列，尝试寻找第一列非空的作为名称
            st.error(f"文件 {file.name} 缺少『产品名称』列，请检查格式。")
            return None

        # 提取月份
        df['所属月份'] = file.name.split('.')[0]
        
        # 字段映射与转换 (融合旧版逻辑)
        col_map = {
            '生产企业（国内一级代理）': '生产厂商',
            '厂商': '生产厂商',
            '耗材名称': '产品名称',
            '结存数量': '仓库结存'
        }
        df.rename(columns=col_map, inplace=True)

        # 数值转换 (完全保留旧版逻辑)
        num_cols = ['数量', '金额', '供应医院价格（单位：元）', '价格', '仓库结存']
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 文本转换 (完全保留旧版逻辑)
        for col in ['产品名称', '型号', '规格', '生产厂商']:
            if col in df.columns:
                df[col] = df[col].astype(str).replace('nan', '-').str.strip()
                
        return df
    except Exception as e:
        st.error(f"解析文件 {file.name} 失败: {e}")
        return None

# --- 4. 处理逻辑 ---
if plan_files:
    all_dfs = [load_and_clean_universal(f, template_type) for f in plan_files]
    all_dfs = [d for d in all_dfs if d is not None]
    
    if all_dfs:
        # 使用 ignore_index=True 合并
        try:
            full_df = pd.concat(all_dfs, ignore_index=True)
        except Exception as e:
            st.error(f"合并文件时出错: {e}。请确保所有上传的计划表格式一致。")
            st.stop()
            
        available_months = sorted(full_df['所属月份'].unique())
        num_months = len(available_months)

        # --- A. 仓库联动逻辑 (仅新版) ---
        if template_type == "新版模式 (计划与仓库联动)" and stock_file:
            s_df = load_and_clean_universal(stock_file, "新版模式")
            if s_df is not None:
                # 汇总库存
                s_sum = s_df.groupby(['产品名称', '生产厂商'])['仓库结存'].sum().reset_index()
                # 合并
                full_df = pd.merge(full_df, s_sum, on=['产品名称', '生产厂商'], how='left')
                full_df['仓库结存'] = full_df['仓库结存'].fillna(0)
                st.sidebar.success("✅ 仓库结存已关联")

        # --- B. 数据概览指标 ---
        st.header(f"📊 采购概览 (共 {num_months} 个月数据)")
        # 兼容旧版选择
        target_col = st.sidebar.selectbox("分析目标", ["数量", "金额"])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("总品种数", f"{full_df['产品名称'].nunique()} 种")
        c2.metric(f"累计{target_col}", f"{full_df[target_col].sum():,.0f}")
        c3.metric(f"月均单品{target_col}", f"{(full_df[target_col].sum() / num_months / full_df['产品名称'].nunique()):,.2f}")

        # --- C. 深度分析表 (均值) ---
        st.header(f"🔍 产品明细与月均值 ({target_col})")
        
        # 计算透视表
        p_idx = ['产品名称', '型号']
        if '生产厂商' in full_df.columns: p_idx.append('生产厂商')
        
        pivot_df = full_df.pivot_table(
            index=p_idx, 
            columns='所属月份', 
            values=target_col, 
            aggfunc='sum'
        ).fillna(0)
        
        pivot_df['累计总计'] = pivot_df.sum(axis=1)
        pivot_df['月均数值'] = pivot_df['累计总计'] / num_months
        pivot_df = pivot_df.sort_values(by='月均数值', ascending=False).reset_index()

        # 如果有库存数据，拼进去
        if '仓库结存' in full_df.columns:
            latest_s = full_df.groupby(p_idx)['仓库结存'].last().reset_index()
            pivot_df = pd.merge(pivot_df, latest_s, on=p_idx, how='left')

        st.dataframe(
            pivot_df.style.background_gradient(subset=['月均数值'], cmap='YlOrRd').format(precision=2),
            use_container_width=True
        )

        # --- D. 变动分析 (较往月) ---
        if num_months >= 2:
            st.header("🆕 采购变动分析 (较上月)")
            curr_m, prev_m = available_months[-1], available_months[-2]
            
            curr_set = set(full_df[full_df['所属月份']==curr_m]['产品名称'] + " | " + full_df[full_df['所属月份']==curr_m]['型号'])
            prev_set = set(full_df[full_df['所属月份']==prev_m]['产品名称'] + " | " + full_df[full_df['所属月份']==prev_m]['型号'])
            
            new_keys = curr_set - prev_set
            if new_keys:
                st.success(f"📌 相比于 {prev_m}，{curr_m} 新增了 {len(new_keys)} 款产品")
                with st.expander("点击查看新增明细"):
                    new_list = [k.split(" | ") for k in new_keys]
                    st.table(pd.DataFrame(new_list, columns=['产品名称', '型号']))
            else:
                st.info("本月无新增产品。")

        # --- E. 可视化排行 ---
        st.subheader("Top 15 产品月均采购排行")
        top_15 = pivot_df.head(15)
        fig = px.bar(top_15, x='产品名称', y='月均数值', color='型号' if '型号' in top_15.columns else None, text_auto='.2s')
        st.plotly_chart(fig, use_container_width=True)

        # --- F. 智能助手 ---
        st.header("🤖 智能分析助手")
        q = st.text_input("您可以提问，例如：'新增了哪些东西？'")
        if q:
            if "新增" in q or "增加" in q:
                st.write("助手：请查看下方的『采购变动分析』板块。")
            elif "最高" in q:
                top_p = pivot_df.iloc[0]['产品名称']
                st.write(f"助手：目前月均{target_col}最高的产品是 **{top_p}**。")
            else:
                st.write("助手：我可以帮您分析新增产品、月均数值和趋势排行。")
else:
    st.info("💡 请在左侧上传文件开始分析。旧版模式只需要上传计划表。")
