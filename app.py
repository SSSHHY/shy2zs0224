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

# --- 新版专用：数值强制转换工具 (处理科学计数法和非数字) ---
def force_numeric(val):
    try:
        if pd.isna(val) or str(val).strip() == "":
            return 0.0
        # 转换为字符串后去掉逗号，再转成浮点数，最后取整（如果是4.00E+31也会被正确转换，虽然数字会很大）
        return float(str(val).replace(',', '').strip())
    except:
        return 0.0

# --- 2. 侧边栏：完全独立的模式选择 ---
st.sidebar.header("⚙️ 模式选择")
mode = st.sidebar.radio(
    "请选择功能模式",
    ["旧版：多月计划对比分析", "新版：计划与仓库联动"]
)

st.sidebar.markdown("---")
st.sidebar.header("📁 上传区域")

# --- 3. 逻辑分离：旧版模式 (完全保持原样，未做改动) ---
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

# --- 4. 逻辑分离：新版模式 (根据需求修改) ---
else:
    plan_files = st.sidebar.file_uploader("1. 上传【新版计划表】", accept_multiple_files=True)
    stock_file = st.sidebar.file_uploader("2. 上传【仓库结存表】")

    def load_new_smart(file):
        try:
            engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
            df_raw = pd.read_excel(file, header=None, engine=engine) if not file.name.endswith('.csv') else pd.read_csv(file, header=None)
            
            # 自动找标题
            header_idx = 0
            for i, row in df_raw.head(20).iterrows():
                # 增加了规格、型号等更多关键词识别标题行
                if any(k in str(val) for val in row.values for k in ["产品名称", "耗材名称", "规格", "型号", "厂家"]):
                    header_idx = i
                    break
            df = df_raw.iloc[header_idx:].copy()
            df.columns = df.iloc[0]
            df = df[1:].reset_index(drop=True)

            # --- 需求1：统一字段名映射 ---
            # 这里的映射涵盖了 耗材->产品, 规格->型号, 厂商->生产厂商
            name_map = {
                '耗材名称': '产品名称', 
                '规格': '型号', 
                '厂商': '生产厂商',
                '生产厂家': '生产厂商',
                '厂家': '生产厂商',
                '结存数量': '仓库库存'
            }
            # 清洗列名两端空格
            df.columns = [str(c).strip() for c in df.columns]
            df.rename(columns=name_map, inplace=True)
            
            # --- 需求2：数值强制转换 (修复 4.00E+31 等错误) ---
            if '仓库库存' in df.columns:
                df['仓库库存'] = df['仓库库存'].apply(force_numeric)
            if '数量' in df.columns:
                df['数量'] = df['数量'].apply(force_numeric)
                
            # 清洗文本字段中的 nan
            for col in ['产品名称', '型号', '生产厂商']:
                if col in df.columns:
                    df[col] = df[col].astype(str).replace('nan', '-').strip()
                    
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
                    # --- 核心改进：多维度组合匹配 ---
                    # 结存表按 (名称+型号+厂商) 汇总，防止由于批次不同导致重复行
                    s_sum = stock_df.groupby(['产品名称', '型号', '生产厂商'])['仓库库存'].sum().reset_index()
                    
                    # 联动合并：基于三个维度对齐
                    merged = pd.merge(
                        full_plan, 
                        s_sum, 
                        on=['产品名称', '型号', '生产厂商'], 
                        how='left'
                    ).fillna(0)
                    
                    st.header("🔍 计划与库存联动清单")
                    # 只展示重点列
                    cols_to_show = ['产品名称', '型号', '生产厂商', '数量', '仓库库存']
                    # 检查列是否存在，避免报错
                    valid_cols = [c for c in cols_to_show if c in merged.columns]
                    st.dataframe(merged[valid_cols], use_container_width=True)
                else:
                    st.error("结存表解析异常，请检查文件。")
            else:
                st.warning("⚠️ 请上传【仓库结存表】以开启计划与库存的自动对齐联动。")
                st.dataframe(full_plan, use_container_width=True)
