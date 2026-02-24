import streamlit as st
import pandas as pd
import plotly.express as px

# 页面配置
st.set_page_config(page_title="医疗器械采购智能分析", layout="wide")

st.title("🏥 医疗器械采购计划智能分析平台")

# --- 1. 文件上传 ---
uploaded_files = st.file_uploader("点击上传多个月份计划表", accept_multiple_files=True, type=['csv', 'xlsx'])

def load_and_clean_data(file):
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, skiprows=3)
        else:
            df = pd.read_excel(file, skiprows=3)
        
        df = df.dropna(subset=['产品名称'])
        # 提取文件名作为月份标识
        month_label = file.name.split('.')[0]
        df['所属月份'] = month_label
        
        # 数值转换
        for col in ['数量', '金额', '供应医院价格（单位：元）']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 文本转换防止报错
        for col in ['产品名称', '型号', '规格']:
            if col in df.columns:
                df[col] = df[col].astype(str).replace('nan', '-')
                
        return df
    except Exception as e:
        st.error(f"解析文件 {file.name} 失败: {e}")
        return None

if uploaded_files:
    all_dfs = [load_and_clean_data(f) for f in uploaded_files if load_and_clean_data(f) is not None]
    
    if all_dfs:
        full_df = pd.concat(all_dfs, ignore_index=True)
        num_months = full_df['所属月份'].nunique() # 获取总月份数
        
        # --- 2. 核心指标卡 ---
        st.header(f"📊 采购概览 (共 {num_months} 个月数据)")
        target_col = st.sidebar.selectbox("分析目标", ["数量", "金额"])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("总品种数", f"{full_df['产品名称'].nunique()} 种")
        c2.metric(f"累计总{target_col}", f"{full_df[target_col].sum():,.0f}")
        c3.metric(f"月均单品{target_col}", f"{(full_df[target_col].sum() / num_months / full_df['产品名称'].nunique()):,.2f}")

        # --- 3. 产品维度深度分析 (新增：计算每个产品的平均值) ---
        st.header(f"🔍 各产品【{target_col}】对比与月均值")
        
        # 建立透视表
        pivot_df = full_df.pivot_table(
            index=['产品名称', '型号'], 
            columns='所属月份', 
            values=target_col, 
            aggfunc='sum'
        ).fillna(0)
        
        # 计算每个产品的平均值：各月总和 / 上传的月份总数
        pivot_df['累计总计'] = pivot_df.sum(axis=1)
        pivot_df['月均数值'] = pivot_df['累计总计'] / num_months
        
        # 排序：按月均数值从高到低
        pivot_df = pivot_df.sort_values(by='月均数值', ascending=False).reset_index()
        
        # 格式化显示
        st.dataframe(
            pivot_df.style.background_gradient(subset=['月均数值'], cmap='YlOrRd').format(precision=2),
            use_container_width=True
        )

        # --- 4. 可视化：Top 15 产品月均值排行 ---
        st.subheader(f"Top 15 产品月均{target_col}排行")
        top_15 = pivot_df.head(15)
        fig = px.bar(top_15, x='产品名称', y='月均数值', color='型号', 
                     text_auto='.2s', title=f"重点产品平均月采购量")
        st.plotly_chart(fig, use_container_width=True)

        # --- 5. 智能助手升级 ---
        st.header("🤖 采购智能助手")
        q = st.text_input("您可以提问，例如：'哪种产品的平均采购量最高？'")
        
        if q:
            if "平均" in q or "均值" in q:
                top_item = pivot_df.iloc[0]
                st.info(f"根据数据分析，**{top_item['产品名称']} ({top_item['型号']})** 的月均{target_col}最高，平均每月采购 **{top_item['月均数值']:.2f}**。")
            elif "对比" in q:
                st.write("您可以查看上方的热力图表格，颜色越深代表该月采购量远高于平均水平。")
            else:
                st.write("助手：您可以尝试询问关于‘月均最高’、‘总额’等问题。")
else:
    st.info("💡 请在左侧上传至少两个月份的采购计划表，系统将自动计算跨月平均值。")