# app.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Delivery Monitoring Dashboard", layout="wide")
st.title("Delivery Monitoring Dashboard")

st.write("上传从 Delivery Monitoring 导出的 Excel/CSV，查看司机完成率和异常司机。")

uploaded_file = st.file_uploader(
    "上传文件（.xlsx / .xls / .csv）",
    type=["xlsx", "xls", "csv"]
)

# 侧边栏参数设置
st.sidebar.header("参数设置")
low_completion_threshold = st.sidebar.slider(
    "完成率低于多少算“比较低”？(%)",
    min_value=0, max_value=100, value=80, step=5
)
inactive_hours_threshold = st.sidebar.slider(
    "Inactive 时间大于多少小时算异常？",
    min_value=1.0, max_value=10.0, value=3.0, step=0.5
)

if uploaded_file is None:
    st.info("请先上传一次 Delivery Monitoring 导出的文件。")
    st.stop()

# 1. 读取数据
if uploaded_file.name.endswith(".csv"):
    df = pd.read_csv(uploaded_file)
else:
    df = pd.read_excel(uploaded_file)

# 清理列名
df.columns = [str(c).strip() for c in df.columns]

st.subheader("原始数据预览")
st.dataframe(df.head(), use_container_width=True)

# 2. 选择关键列：司机、Route、完成率、Inactive、To be delivered/Total
with st.expander("列映射设置（如果自动识别不对，可以手动修改）", expanded=True):
    # 猜测 driver 列
    driver_candidates = [c for c in df.columns if "driver" in c.lower() or "d.." in c.lower()]
    driver_col = st.selectbox(
        "司机列（Driver）",
        options=df.columns.tolist(),
        index=df.columns.get_loc(driver_candidates[0]) if driver_candidates else 0
    )

    # route 列（你后面要按这个分组）
    route_col = st.selectbox(
        "Route / Team 列（可选，用来区分路线）",
        options=["<不使用 Route 列>"] + df.columns.tolist(),
        index=0
    )

    # completion rate 列
    comp_candidates = [c for c in df.columns if "completion" in c.lower()]
    comp_col = st.selectbox(
        "Completion Rate 列",
        options=df.columns.tolist(),
        index=df.columns.get_loc(comp_candidates[0]) if comp_candidates else 0
    )

    # inactive 时间列
    inact_candidates = [c for c in df.columns if "inactive" in c.lower()]
    inactive_col = st.selectbox(
        "Inactive Time 列",
        options=df.columns.tolist(),
        index=df.columns.get_loc(inact_candidates[0]) if inact_candidates else 0
    )

    # to be delivered/total 列
    tbd_candidates = [c for c in df.columns if "to be" in c.lower() or "delivered/total" in c.lower()]
    tbd_col = st.selectbox(
        "To be delivered/Total 列",
        options=df.columns.tolist(),
        index=df.columns.get_loc(tbd_candidates[0]) if tbd_candidates else 0
    )

# 3. 解析 To be delivered/Total
tbd_split = df[tbd_col].astype(str).str.split("/", expand=True)
df["to_be_delivered"] = pd.to_numeric(tbd_split[0], errors="coerce").fillna(0).astype(int)
df["total_packages"] = pd.to_numeric(tbd_split[1], errors="coerce").fillna(0).astype(int)
df["delivered"] = df["total_packages"] - df["to_be_delivered"]

# 4. 解析 Completion Rate（转成数值百分比）
df["completion_rate_pct"] = (
    df[comp_col]
    .astype(str)
    .str.rstrip("%")
    .replace("", np.nan)
)
df["completion_rate_pct"] = pd.to_numeric(df["completion_rate_pct"], errors="coerce")

# 5. 解析 Inactive 时间（HH:MM:SS → 小时）
def parse_time_to_hours(x):
    x = str(x)
    if ":" not in x:
        return np.nan
    parts = x.split(":")
    if len(parts) != 3:
        return np.nan
    h, m, s = parts
    try:
        h = int(h)
        m = int(m)
        s = int(s)
        return h + m / 60 + s / 3600
    except Exception:
        return np.nan

df["inactive_hours"] = df[inactive_col].apply(parse_time_to_hours)

# 6. 总体完成率
if df["total_packages"].sum() > 0:
    overall_completion = df["delivered"].sum() / df["total_packages"].sum()
else:
    overall_completion = 0.0

st.subheader("总体完成情况")
col1, col2, col3 = st.columns(3)
col1.metric("Overall Completion Rate", f"{overall_completion * 100:.1f}%")
col2.metric("Total Packages", int(df["total_packages"].sum()))
col3.metric("Remaining Packages", int(df["to_be_delivered"].sum()))

# 7. 每个司机完成率图表
st.subheader("按司机完成率（柱状图）")

driver_group = (
    df.groupby(driver_col, as_index=False)
    .agg(
        completion_rate_pct=("completion_rate_pct", "mean"),
        delivered=("delivered", "sum"),
        to_be_delivered=("to_be_delivered", "sum"),
        total_packages=("total_packages", "sum"),
        inactive_hours=("inactive_hours", "max"),  # 取该司机最大 inactive 时间
    )
)

st.dataframe(
    driver_group.sort_values("completion_rate_pct", ascending=False),
    use_container_width=True,
)

# bar chart
chart_df = (
    driver_group[["completion_rate_pct", driver_col]]
    .set_index(driver_col)
    .sort_values("completion_rate_pct", ascending=False)
)
st.bar_chart(chart_df)

# 8. 自动筛选：inactive > 阈值 & 完成率低
st.subheader("异常司机（Inactive 时间过长且完成率偏低）")

mask = (
    (driver_group["inactive_hours"] >= inactive_hours_threshold)
    & (driver_group["completion_rate_pct"] < low_completion_threshold)
)

flagged = driver_group.loc[mask].copy()

# 如果有 route 列，就把 route 信息也加上（一个司机可能多个 route，这里简单取出现次数最多的）
if route_col != "<不使用 Route 列>":
    route_map = (
        df[[driver_col, route_col]]
        .dropna()
        .groupby(driver_col)[route_col]
        .agg(lambda x: x.value_counts().index[0])  # 最常见的 route
        .to_dict()
    )
    flagged["Route"] = flagged[driver_col].map(route_map)

if flagged.empty:
    st.success("目前没有满足条件的异常司机。")
else:
    show_cols = [driver_col]
    if "Route" in flagged.columns:
        show_cols.append("Route")
    show_cols += [
        "completion_rate_pct",
        "inactive_hours",
        "delivered",
        "to_be_delivered",
        "total_packages",
    ]
    st.warning(f"共发现 {len(flagged)} 名异常司机：")
    st.dataframe(
        flagged[show_cols].sort_values("completion_rate_pct"),
        use_container_width=True,
    )
