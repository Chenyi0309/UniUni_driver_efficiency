# app.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import altair as alt

st.set_page_config(page_title="UniUni Driver Completion Dashboard", layout="wide")
st.title("UniUni Driver Completion Dashboard")

# ==============================
# 1. 默认 Route → Driver 映射
# ==============================
DEFAULT_ROUTE_MAP = {
    2:  [20025, 20032, 20038, 20041, 44776, 46353, 94361, 5004645, 5006742],
    3:  [60911, 93787, 95091, 96528, 5003395, 5005937, 5006711,
         5200583, 5201764, 5202196, 5202457, 5205698, 5207998, 5217073],
    6:  [31976, 54274, 94870, 5002004, 5005943, 5009726, 5205299],
    9:  [79638, 86494, 86495, 88016, 5203839],
    10: [11150, 11167, 39871, 44640, 5216349],
    11: [44650],
    12: [89828, 5201554, 5201598, 5201602, 5207482, 5209676,
         5210936, 5216145, 5216152],
    17: [11154, 5205901],
    19: [37621, 37626, 5007017, 5209368, 5215916],
    20: [86492, 87043, 5000938],
    "UPS": [5215914],
}

JSON_FILE = "route_map.json"

# =========================================
# 2. 加载 / 保存用户新增的 Route 映射
# =========================================
def load_saved_map():
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            return {}
        result = {}
        for k, v in data.items():
            # key 可能是数字也可能是字符串（比如 "UPS"）
            try:
                key = int(k)
            except:
                key = k
            result[key] = list({int(d) for d in v})
        return result
    return {}

def save_route_map(route_map):
    # 写文件时把 key 都变成字符串，driver id 变成 int 列表
    serializable = {}
    for k, v in route_map.items():
        serializable[str(k)] = [int(d) for d in v]
    with open(JSON_FILE, "w") as f:
        json.dump(serializable, f, indent=4)

SAVED_MAP = load_saved_map()

# 合并默认映射和用户映射
ROUTE_MAP = DEFAULT_ROUTE_MAP.copy()
for r, drivers in SAVED_MAP.items():
    if r in ROUTE_MAP:
        ROUTE_MAP[r] = list(set(ROUTE_MAP[r] + drivers))
    else:
        ROUTE_MAP[r] = drivers

# ==========================
# 3. 侧边栏：新增 Driver → Route
# ==========================
st.sidebar.subheader("添加新的 Driver → Route 映射")

new_driver = st.sidebar.text_input("Driver ID（例如 5201554）")
new_route = st.sidebar.text_input("Route Number（例如 12 或 UPS）")

if st.sidebar.button("保存映射"):
    if new_driver and new_route:
        try:
            driver_id = int(new_driver)
        except ValueError:
            st.sidebar.error("Driver ID 必须是数字")
        else:
            # route 可以是数字也可以是字符串
            try:
                route_id = int(new_route)
            except ValueError:
                route_id = new_route

            # 更新 SAVED_MAP，然后写回文件
            key = str(route_id)
            existing = SAVED_MAP.get(key, [])
            if driver_id not in existing:
                existing.append(driver_id)
            SAVED_MAP[key] = existing
            # 和 DEFAULT_ROUTE_MAP 合并后再保存
            temp_map = DEFAULT_ROUTE_MAP.copy()
            for rk, rv in SAVED_MAP.items():
                try:
                    rk2 = int(rk)
                except ValueError:
                    rk2 = rk
                if rk2 in temp_map:
                    temp_map[rk2] = list(set(temp_map[rk2] + rv))
                else:
                    temp_map[rk2] = rv
            save_route_map(temp_map)
            st.sidebar.success(f"已保存：Driver {driver_id} → Route {route_id}")
    else:
        st.sidebar.error("请填写完整 Driver 和 Route")

# ==========================
# 4. 阈值设置
# ==========================
st.sidebar.markdown("---")
st.sidebar.header("异常司机阈值")

low_completion_threshold = st.sidebar.slider(
    "完成率低于多少算“比较低”？(%)",
    min_value=0, max_value=100, value=80, step=5
)

inactive_hours_threshold = st.sidebar.slider(
    "Inactive 时间大于多少小时算异常？",
    min_value=1.0, max_value=10.0, value=3.0, step=0.5
)

# ==========================
# 5. 上传数据
# ==========================
uploaded_file = st.file_uploader(
    "上传 Delivery Monitoring 导出的 Excel（xlsx/csv）",
    type=["xlsx", "csv"]
)

if uploaded_file is None:
    st.info("请上传 driverEfficiency 之类的导出文件。")
    st.stop()

if uploaded_file.name.endswith(".csv"):
    df = pd.read_csv(uploaded_file)
else:
    df = pd.read_excel(uploaded_file)

# 列名统一处理：转为字符串再 strip，避免 .strip() 报错
df.columns = [str(c).strip() for c in df.columns]

# ==========================
# 6. 关键列自动识别
# ==========================
# 司机列
driver_candidates = [c for c in df.columns if "driver" in c.lower()]
driver_col = driver_candidates[0] if driver_candidates else df.columns[0]

# To be delivered/Total 列
tbd_candidates = [c for c in df.columns if "to be" in c.lower() or "delivered/total" in c.lower()]
tbd_col = tbd_candidates[0] if tbd_candidates else df.columns[-5]

# Completion Rate 列
comp_candidates = [c for c in df.columns if "completion" in c.lower()]
comp_col = comp_candidates[0] if comp_candidates else df.columns[-4]

# Inactive Time 列
inactive_candidates = [c for c in df.columns if "inactive" in c.lower()]
inactive_col = inactive_candidates[0] if inactive_candidates else df.columns[-1]

st.subheader("原始数据预览")
st.write(f"识别的列：Driver = `{driver_col}`, ToBe/Total = `{tbd_col}`, "
         f"Completion = `{comp_col}`, Inactive = `{inactive_col}`")
st.dataframe(df.head(), use_container_width=True)

# ==========================
# 7. 字段解析
# ==========================
# 7.1 To be delivered / Total
split = df[tbd_col].astype(str).str.split("/", expand=True)
df["to_be"] = pd.to_numeric(split[0], errors="coerce").fillna(0).astype(int)
df["total"] = pd.to_numeric(split[1], errors="coerce").fillna(0).astype(int)
df["delivered"] = df["total"] - df["to_be"]

# 7.2 Completion Rate 数值化
df["completion"] = (
    df[comp_col]
    .astype(str)
    .str.rstrip("%")
    .replace("", np.nan)
)
df["completion"] = pd.to_numeric(df["completion"], errors="coerce")

# 7.3 Inactive 时间转小时
def time_to_hours(x):
    s = str(x)
    if ":" not in s:
        return np.nan
    parts = s.split(":")
    if len(parts) != 3:
        return np.nan
    try:
        h, m, s = map(int, parts)
        return h + m / 60 + s / 3600
    except Exception:
        return np.nan

df["inactive_hours"] = df[inactive_col].apply(time_to_hours)

# 7.4 分配 Route
def assign_route(driver):
    try:
        d = int(driver)
    except Exception:
        return "UNASSIGNED"
    for route, drivers in ROUTE_MAP.items():
        if d in drivers:
            return route
    return "UNASSIGNED"

df["route"] = df[driver_col].apply(assign_route)

# ==========================
# 8. 汇总到司机层级
# ==========================
driver_group = (
    df.groupby([driver_col, "route"], as_index=False)
    .agg(
        completion_rate_pct=("completion", "mean"),
        delivered=("delivered", "sum"),
        to_be=("to_be", "sum"),
        total=("total", "sum"),
        inactive_hours=("inactive_hours", "max"),
    )
)

# 总体完成情况
if driver_group["total"].sum() > 0:
    overall_completion = driver_group["delivered"].sum() / driver_group["total"].sum()
else:
    overall_completion = 0.0

st.subheader("总体完成情况")
c1, c2, c3 = st.columns(3)
c1.metric("Overall Completion Rate", f"{overall_completion * 100:.1f}%")
c2.metric("Total Packages", int(driver_group["total"].sum()))
c3.metric("Remaining Packages", int(driver_group["to_be"].sum()))

# ==========================
# 9. 图表：按 Route 着色
# ==========================
st.subheader("按司机完成率（按 Route 着色）")

chart_route = (
    alt.Chart(driver_group)
    .mark_bar()
    .encode(
        x=alt.X("completion_rate_pct:Q", title="Completion Rate (%)"),
        y=alt.Y(f"{driver_col}:N", sort="-x", title="Driver ID"),
        color=alt.Color("route:N", title="Route"),
        tooltip=[driver_col, "route", "completion_rate_pct", "inactive_hours"]
    )
    .properties(height=600)
)

st.altair_chart(chart_route, use_container_width=True)

# ==========================
# 10. 图表：普通完成率柱状图
# ==========================
st.subheader("按司机完成率（普通柱状图）")

simple_chart_data = driver_group[[driver_col, "completion_rate_pct"]].sort_values(
    "completion_rate_pct", ascending=False
)

chart_simple = (
    alt.Chart(simple_chart_data)
    .mark_bar()
    .encode(
        x=alt.X("completion_rate_pct:Q", title="Completion Rate (%)"),
        y=alt.Y(f"{driver_col}:N", sort="-x", title="Driver ID"),
        tooltip=[driver_col, "completion_rate_pct"]
    )
    .properties(height=600)
)

st.altair_chart(chart_simple, use_container_width=True)

# ==========================
# 11. 异常司机筛选
# ==========================
st.subheader("异常司机（Inactive 过长 & 完成率偏低）")

mask = (
    (driver_group["inactive_hours"] >= inactive_hours_threshold)
    & (driver_group["completion_rate_pct"] < low_completion_threshold)
)

flagged = driver_group.loc[mask].copy()

if flagged.empty:
    st.success("目前没有满足条件的异常司机。")
else:
    st.warning(f"共发现 {len(flagged)} 名异常司机：")
    display_cols = [
        driver_col, "route",
        "completion_rate_pct", "inactive_hours",
        "delivered", "to_be", "total",
    ]
    st.dataframe(
        flagged[display_cols].sort_values("completion_rate_pct"),
        use_container_width=True,
    )
