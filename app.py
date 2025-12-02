# app.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import altair as alt

st.set_page_config(page_title="UniUni Driver Dashboard", layout="wide")
st.title("UniUni Driver Completion Dashboard")

# ==============================
# 1. 默认的 Route → Driver 映射
# ==============================
DEFAULT_ROUTE_MAP = {
    2:  [20025, 20032, 20038, 20041, 44776, 46353, 94361, 5004645, 5006742],
    3:  [60911, 93787, 95091, 96528, 5003395, 5005937, 5006711, 5200583, 5201764, 5202196, 5202457, 5205698, 5207998, 5217073],
    6:  [31976, 54274, 94870, 5002004, 5005943, 5009726, 5205299],
    9:  [79638, 86494, 86495, 88016, 5203839],
    10: [11150, 11167, 39871, 44640, 5216349],
    11: [44650],
    12: [89828, 5201554, 5201598, 5201602, 5207482, 5209676, 5210936, 5216145, 5216152],
    17: [11154, 5205901],
    19: [37621, 37626, 5007017, 5209368, 5215916],
    20: [86492, 87043, 5000938],
    "UPS": [5215914],
}

JSON_FILE = "route_map.json"

# =========================================
# 2. 加载用户添加过的 route 映射（持久化）
# =========================================
def load_saved_map():
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r") as f:
            try:
                data = json.load(f)
                # JSON 的 key 是字符串，需要转成 int 或保留特殊名字
                result = {}
                for k, v in data.items():
                    try:
                        k2 = int(k)
                    except:
                        k2 = k
                    result[k2] = v
                return result
            except:
                return {}
    return {}

def save_route_map(route_map):
    with open(JSON_FILE, "w") as f:
        json.dump(route_map, f, indent=4)

SAVED_MAP = load_saved_map()

# 合并默认映射 + 追加映射
ROUTE_MAP = DEFAULT_ROUTE_MAP.copy()
for r, drivers in SAVED_MAP.items():
    if r in ROUTE_MAP:
        ROUTE_MAP[r] = list(set(ROUTE_MAP[r] + drivers))
    else:
        ROUTE_MAP[r] = drivers

# ==========================
# 3. 添加新 driver 映射 UI
# ==========================
st.sidebar.subheader("添加新的 Driver → Route 映射")

new_driver = st.sidebar.text_input("Driver ID（例如 5201554）")
new_route = st.sidebar.text_input("Route Number（例如 12 或 UPS）")

if st.sidebar.button("保存映射"):
    if new_driver and new_route:
        try:
            driver_id = int(new_driver)
        except:
            st.sidebar.error("Driver ID 必须是数字")
            st.stop()

        try:
            route_id = int(new_route)
        except:
            route_id = new_route  # 允许 UPS 这种

        existing = SAVED_MAP.get(str(route_id), [])
        if driver_id not in existing:
            existing.append(driver_id)
        SAVED_MAP[str(route_id)] = existing
        save_route_map(SAVED_MAP)
        st.sidebar.success(f"已保存：Driver {driver_id} → Route {route_id}")
    else:
        st.sidebar.error("请填写完整")

# ==========================
# 4. 上传数据
# ==========================
uploaded_file = st.file_uploader("上传 Delivery Monitoring 导出的 Excel（xlsx/csv）", type=["xlsx", "csv"])

if uploaded_file is None:
    st.info("请上传文件。")
    st.stop()

# 读取数据
if uploaded_file.name.endswith(".csv"):
    df = pd.read_csv(uploaded_file)
else:
    df = pd.read_excel(uploaded_file)
df.columns = [c.strip() for c in df.columns]

# ========== 必要列 ==========
driver_col = "D.." if "D.." in df.columns else df.columns[1]
tbd_col = [c for c in df.columns if "to" in c.lower()][0]
comp_col = [c for c in df.columns if "completion" in c.lower()][0]
inactive_col = [c for c in df.columns if "inactive" in c.lower()][0]

# ========== 解析 To be delivered/Total ==========
split = df[tbd_col].astype(str).str.split("/", expand=True)
df["to_be"] = split[0].astype(int)
df["total"] = split[1].astype(int)
df["delivered"] = df["total"] - df["to_be"]

# ========== 解析完成率 ==========
df["completion"] = df[comp_col].astype(str).str.rstrip("%").astype(float)

# ========== inactive 时间转小时 ==========
def conv(x):
    try:
        h, m, s = str(x).split(":")
        return int(h) + int(m)/60 + int(s)/3600
    except:
        return np.nan

df["inactive_hours"] = df[inactive_col].apply(conv)

# ========== route 分配 ==========
def assign_route(driver):
    driver = int(driver)
    for route, drivers in ROUTE_MAP.items():
        if driver in drivers:
            return route
    return "UNASSIGNED"

df["route"] = df[driver_col].apply(assign_route)

# ==========================
# 5. 图表（按 route 着色）
# ==========================
st.subheader("按司机完成率柱状图（按 Route 着色）")

chart_data = df.groupby([driver_col, "route"], as_index=False)["completion"].mean()

chart = (
    alt.Chart(chart_data)
    .mark_bar()
    .encode(
        x=alt.X("completion:Q", title="Completion Rate (%)"),
        y=alt.Y(f"{driver_col}:N", sort="-x", title="Driver ID"),
        color=alt.Color("route:N", title="Route"),
        tooltip=[driver_col, "route", "completion"]
    )
    .properties(height=600)
)

st.altair_chart(chart, use_container_width=True)

# ==========================
# 6. 异常司机筛选
# ==========================
st.subheader("异常司机（Inactive > 3 小时 且 Completion 较低）")

mask = (df["inactive_hours"] >= 3) & (df["completion"] < 80)

bad = df.loc[mask, [driver_col, "route", "completion", "inactive_hours", "delivered", "to_be", "total"]]

if bad.empty:
    st.success("没有找到异常司机。")
else:
    st.warning(f"共发现 {len(bad)} 名异常司机")
    st.dataframe(bad, use_container_width=True)
