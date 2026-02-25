import streamlit as st
import pandas as pd

# ==========================================
# 1. 页面配置与函数保持不变 (load_data_old, load_data_new_smart)
# ==========================================
st.set_page_config(page_title="医疗器械采购智能分析平台", layout="wide")

def load_data_old(file):
    try:
        engine = 'xlrd' if file.name.endswith('.xls') else 'openpyxl'
        df = pd.read_csv(file, skiprows=3) if file.name.endswith('.csv') else pd.read_excel(file, skiprows=3, engine=engine)
        df.columns = [f"{c}_{i}" if list(df.columns).count(c) > 1 else c for i, c in enumerate(df.columns)]
        df = df.dropna(subset=['产品名称'])
        df['所属月份'] = file.name.split('.')[0]
        for col in ['数量', '金额']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"解析 {file.name} 失败: {e}")
        return None

# ==========================================
# 2. 主界面逻辑
# ==========================================
st.sidebar.title("🛠️ 控制面板")
mode = st.sidebar.radio("选择分析模式", ["旧版：多月计划对比", "新版：计划/仓库联动"])

if mode == "旧版：多月计划对比":
    st.sidebar.subheader("📁 上传区域")
    uploaded_files = st.sidebar.file_uploader("上传多个月份计划表", accept_multiple_files=True)

    if uploaded_files:
        all_dfs = [load_data_old(f) for f in uploaded_files if load_data_old(f) is not None]
        
        if all_dfs:
            full_df_all = pd.concat(all_dfs, ignore_index=True)
            available_months = sorted(full_df_all['所属月份'].unique(), reverse=True) # 降序排列，通常最新月份在后

            # --- 核心修改：双选框模式 ---
            st.sidebar.subheader("📅 时间对比设置")
            col_curr = st.sidebar.selectbox("选择当前月 (分析目标)", available_months, index=0)
            
            # 排除掉当前月，剩下的作为对比月备选
            remaining_months = [m for m in available_months if m != col_curr]
            if remaining_months:
                col_prev = st.sidebar.selectbox("选择对比月 (参照基准)", remaining_months, index=0)
            else:
                col_prev = None
                st.sidebar.warning("请至少上传两个月份的文件进行对比。")

            target_col = st.sidebar.selectbox("分析指标", ["数量", "金额"])

            # --- 3. 渲染分析界面 ---
            if col_curr and col_prev:
                st.title(f"📊 采购对比分析：{col_curr} vs {col_prev}")
                
                # 提取两个月的数据
                df_curr = full_df_all[full_df_all['所属月份'] == col_curr]
                df_prev = full_df_all[full_df_all['所属月份'] == col_prev]

                # 指标计算
                val_curr = df_curr[target_col].sum()
                val_prev = df_prev[target_col].sum()
                delta_val = val_curr - val_prev
                delta_ratio = (delta_val / val_prev * 100) if val_prev != 0 else 0

                # 顶部卡片
                c1, c2, c3 = st.columns(3)
                c1.metric(f"{col_curr} 总{target_col}", f"{val_curr:,.2f}")
                c2.metric(f"{col_prev} 总{target_col}", f"{val_prev:,.2f}")
                c3.metric("环比增减", f"{delta_val:,.2f}", f"{delta_ratio:.1f}%")

                # --- 4. 数据透视表 ---
                st.divider()
                st.subheader("🔍 单品明细对比")
                
                # 合并数据
                p_curr = df_curr.groupby(['产品名称', '型号'])[target_col].sum().reset_index()
                p_prev = df_prev.groupby(['产品名称', '型号'])[target_col].sum().reset_index()
                
                merged = pd.merge(p_curr, p_prev, on=['产品名称', '型号'], how='outer', suffixes=(f'_{col_curr}', f'_{col_prev}')).fillna(0)
                
                # 计算差异
                col_name_curr = f"{target_col}_{col_curr}"
                col_name_prev = f"{target_col}_{col_prev}"
                merged['差异值'] = merged[col_name_curr] - merged[col_name_prev]
                
                # 排序并展示
                merged = merged.sort_values(by='差异值', ascending=False)
                
                st.dataframe(
                    merged.style.background_gradient(subset=['差异值'], cmap='RdYlGn_r') # 红色代表增加，绿色代表减少
                    .format(precision=2),
                    use_container_width=True
                )

                # --- 5. 特殊状态分析 ---
                col_a, col_b = st.columns(2)
                with col_a:
                    st.success(f"✨ {col_curr} 新增品种")
                    new_items = merged[merged[col_name_prev] == 0][['产品名称', '型号', col_name_curr]]
                    st.dataframe(new_items.head(10), use_container_width=True)
                
                with col_b:
                    st.error(f"🚫 {col_curr} 缺失品种 (对比 {col_prev})")
                    missing_items = merged[merged[col_name_curr] == 0][['产品名称', '型号', col_name_prev]]
                    st.dataframe(missing_items.head(10), use_container_width=True)
            else:
                st.info("💡 请在左侧选择需要对比的月份。")

# --- 新版联动模式部分代码保持不变 ---
