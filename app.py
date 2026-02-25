import streamlit as st
import pandas as pd
import plotly.express as px

# ==========================================
# 1. 页面配置
# ==========================================
st.set_page_config(page_title="医疗器械采购智能分析", layout="wide")

st.title("🏥 医疗器械采购计划智能分析平台")

# --- 样式补丁 ---
st.markdown("""
    <style>
    .main .block-container { overflow-y: auto !important; }
    html, body, [data-testid="stAppViewContainer"] { overflow: visible !important; }
    .stMetric { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 数据处理函数
# ==========================================
def load_and_clean_data(file):
    try:
        # 根据后缀名选择读取方式
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, skiprows=3)
        elif file.name.endswith('.xls'):
            df = pd.read_excel(file, skiprows=3, engine='xlrd')
        else:
            df = pd.read_excel(file, skiprows=3, engine='openpyxl')
        
        # 基础清洗
        df = df.dropna(subset=['产品名称'])
        month_label = file.name.split('.')[0]
        df['所属月份'] = month_label
        
        # 数值转换
        for col in ['数量', '金额', '供应医院价格（单位：元）']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 文本转换
        for col in ['产品名称', '型号', '规格']:
            if col in df.columns:
                df[col] = df[col].astype(str).replace('nan', '-')
                
        return df
    except Exception as e:
        st.error(f"解析文件 {file.name} 失败: {e}")
        return None

# ==========================================
# 3. 侧边栏：文件上传与参数设置
# ==========================================
st.sidebar.header("📁 数据上传")
uploaded_files = st.sidebar.file_uploader("上传多个月份计划表", accept_multiple_files=True, type=['csv', 'xlsx', 'xls'])

if uploaded_files:
    all_dfs = [load_and_clean_data(f) for f in uploaded_files if load_and_clean_data(f) is not None]
    
    if all_dfs:
        full_df = pd.concat(all_dfs, ignore_index=True)
        available_months = sorted(full_df['所属月份'].unique(), reverse=True)
        
        st.sidebar.markdown("---")
        st.sidebar.header("🎯 对比设置")
        
        # 核心修改：当前月 vs 对比月
        curr_m = st.sidebar.selectbox("选择当前月 (分析目标)", available_months, index=0)
        remaining_months = [m for m in available_months if m != curr_m]
        
        if remaining_months:
            prev_m = st.sidebar.selectbox("选择对比月 (参照基准)", remaining_months, index=0)
        else:
            prev_m = None
            st.sidebar.warning("上传更多月份以启用对比。")
            
        target_col = st.sidebar.selectbox("分析目标", ["数量", "金额"])

        # ==========================================
        # 4. 核心指标展示 (基于选中的当前月)
        # ==========================================
        curr_data = full_df[full_df['所属月份'] == curr_m]
        prev_data = full_df[full_df['所属月份'] == prev_m] if prev_m else pd.DataFrame()

        st.header(f"📊 {curr_m} 采购概览")
        
        c1, c2, c3 = st.columns(3)
        total_items = curr_data['产品名称'].nunique()
        total_val = curr_data[target_col].sum()
        
        # 计算相对于对比月的增幅
        delta_val = None
        if not prev_data.empty:
            prev_total_val = prev_data[target_col].sum()
            delta_val = f"{((total_val - prev_total_val)/prev_total_val*100):+.1f}%" if prev_total_val != 0 else None

        c1.metric("当月品种数", f"{total_items} 种")
        c2.metric(f"当月总{target_col}", f"{total_val:,.0f}", delta=delta_val)
        
        # 计算选定月份的平均值（参考原代码逻辑）
        avg_val = full_df.groupby(['产品名称', '型号'])[target_col].sum().sum() / len(available_months) / full_df['产品名称'].nunique()
        c3.metric("全周期月均单品", f"{avg_val:,.2f}")

        # ==========================================
        # 5. 产品维度深度分析 (透视表)
        # ==========================================
        st.divider()
        st.header(f"🔍 各产品【{target_col}】对比与月均值")
        
        # 仅针对上传的所有月份做透视
        pivot_df = full_df.pivot_table(
            index=['产品名称', '型号'], 
            columns='所属月份', 
            values=target_col, 
            aggfunc='sum'
        ).fillna(0)
        
        pivot_df['累计总计'] = pivot_df.sum(axis=1)
        pivot_df['月均数值'] = pivot_df['累计总计'] / len(available_months)
        pivot_df = pivot_df.sort_values(by='月均数值', ascending=False).reset_index()
        
        st.dataframe(
            pivot_df.style.background_gradient(subset=['月均数值'], cmap='YlOrRd').format(precision=2),
            use_container_width=True
        )

        # ==========================================
        # 6. 采购变动分析 (针对选择的两个月)
        # ==========================================
        st.divider()
        st.header(f"🆕 采购变动分析 ({curr_m} vs {prev_m if prev_m else '无'})")
        
        if prev_m:
            curr_set = set(curr_data['产品名称'] + " | " + curr_data['型号'])
            prev_set = set(prev_data['产品名称'] + " | " + prev_data['型号'])
            
            # 计算新增
            new_items_keys = curr_set - prev_set
            
            if new_items_keys:
                st.success(f"📌 相比于 {prev_m}，{curr_m} **新增**了 {len(new_items_keys)} 款产品：")
                
                new_items_list = []
                for item in new_items_keys:
                    name, model = item.split(" | ")
                    detail = curr_data[(curr_data['产品名称'] == name) & (curr_data['型号'] == model)].iloc[0]
                    new_items_list.append({
                        "产品名称": name,
                        "型号": model,
                        "当前月数量": detail['数量'],
                        "当前月金额": detail['金额'],
                        "单价": detail.get('供应医院价格（单位：元）', 0),
                        "备注": detail.get('备注', '-')
                    })
                st.table(pd.DataFrame(new_items_list))
            else:
                st.info(f"✅ {curr_m} 相对 {prev_m} 没有新增品种。")
        else:
            st.warning("⚠️ 请上传至少两个月份的表格。")

        # ==========================================
        # 7. 可视化与助手
        # ==========================================
        st.divider()
        st.subheader(f"Top 15 产品月均{target_col}排行")
        top_15 = pivot_df.head(15)
        fig = px.bar(top_15, x='产品名称', y='月均数值', color='型号', 
                     text_auto='.2s', title="重点产品平均月采购趋势")
        st.plotly_chart(fig, use_container_width=True)

        st.header("🤖 采购智能助手")
        q = st.text_input("您可以提问，例如：'新增了哪些东西？'")
        if q:
            if "新增" in q or "增加" in q:
                st.write(f"助手：对比 {prev_m}，{curr_m} 新增了 {len(new_items_keys) if prev_m else 0} 项产品，详情请见上方表格。")
            elif "最高" in q or "均值" in q:
                top_item = pivot_df.iloc[0]
                st.info(f"分析结果：**{top_item['产品名称']}** 月均{target_col}达 {top_item['月均数值']:.2f}，排名第一。")
            else:
                st.write("助手：我可以帮您分析新增变动或寻找均值最高的产品。")

else:
    st.info("💡 请在左侧上传至少两个月份的采购计划表。")
