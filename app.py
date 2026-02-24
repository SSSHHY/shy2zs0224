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
            # 默认对比最后两个月
            col_m1, col_m2 = st.columns(2)
            curr_m = col_m1.selectbox("选择当前月", available_months, index=num_months-1)
            prev_m = col_m2.selectbox("选择对比月", available_months, index=num_months-2)
            
            # 提取两个月的数据集合 (以名称+型号作为唯一标识)
            curr_data = full_df[full_df['所属月份'] == curr_m]
            prev_data = full_df[full_df['所属月份'] == prev_m]
            
            curr_set = set(curr_data['产品名称'] + " | " + curr_data['型号'])
            prev_set = set(prev_data['产品名称'] + " | " + prev_data['型号'])
            
            # 计算新增
            new_items_keys = curr_set - prev_set
            
            if new_items_keys:
                st.success(f"📌 相比于 {prev_m}，{curr_m} **新增**了 {len(new_items_keys)} 款产品：")
                
                # 将 Key 转回 DataFrame 显示明细
                new_items_list = []
                for item in new_items_keys:
                    name, model = item.split(" | ")
                    # 获取该产品在当前月的详细信息（如单价、数量）
                    detail = curr_data[(curr_data['产品名称'] == name) & (curr_data['型号'] == model)].iloc[0]
                    new_items_list.append({
                        "产品名称": name,
                        "型号": model,
                        "当前月数量": detail['数量'],
                        "单价": detail['供应医院价格（单位：元）'],
                        "备注": detail['备注']
                    })
                
                st.table(pd.DataFrame(new_items_list))
            else:
                st.info(f"✅ {curr_m} 相对 {prev_m} 没有新增品种。")
        else:
            st.warning("⚠️ 请至少上传两个月份的表格来分析新增变动。")

        # --- 5. 可视化 ---
        st.subheader(f"Top 15 产品月均{target_col}排行")
        top_15 = pivot_df.head(15)
        fig = px.bar(top_15, x='产品名称', y='月均数值', color='型号', 
                     text_auto='.2s', title=f"重点产品平均月采购量")
        st.plotly_chart(fig, use_container_width=True)

        # --- 6. 智能助手 ---
        st.header("🤖 采购智能助手")
        q = st.text_input("您可以提问，例如：'新增了哪些东西？'")
        
        if q:
            if "新增" in q or "增加" in q:
                st.write("助手：请查看下方的『采购变动分析』板块，已为您列出本月新采购的明细表。")
            elif "平均" in q or "均值" in q:
                top_item = pivot_df.iloc[0]
                st.info(f"根据数据分析，**{top_item['产品名称']}** 的月均{target_col}最高，平均每月 **{top_item['月均数值']:.2f}**。")
            else:
                st.write("助手：您可以尝试询问关于‘新增’、‘月均最高’、‘总额’等问题。")
else:
    st.info("💡 请在左侧上传至少两个月份的采购计划表，系统将自动计算跨月平均值及新增变动。")
