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
# 1. 默认 分类 → Driver 映射
# ==============================
DEFAULT_GROUP_MAP = {
    "DING DONG": [
        60911, 93787, 95091, 96528, 5003395, 5005937, 5006711,
        5200583, 5201764, 5202196, 5202457, 5205698, 5207998, 5217073,
        31976, 54274, 94870, 5002004, 5005943, 5009726, 5205299,
    ],
    "SPEEDY": [
        20025, 20032, 20038, 20041, 44776, 46353, 94361, 5004645, 5006742,
        79638, 86494, 86495, 88016, 5203839,
        86492, 87043, 5000938,
    ],
    "ANDY": [
        11150, 11167, 39871, 44640, 5216349,
        44650,
        11154, 5205901,
        37621, 37626, 5007017, 5209368, 5215916,
    ],
    "Route 12": [
        89828, 5201554, 5201598, 5201602, 5207482,
        5209676, 5210936, 5216145, 5216152,
    ],
}

# 下拉菜单显示内容（让你记得路线编号）
GROUP_OPTIONS = [
    "DING DONG (3, 6)",
    "SPEEDY (2, 9, 20)",
    "ANDY (10, 11, 17, 19)",
    "Route 12 (12)",
]

# 显示值 → 内部分类名
DISPLAY_TO_INTERNAL = {
    "DING DONG (3, 6)": "DING DONG",
    "SPEEDY (2, 9, 20)": "SPEEDY",
    "ANDY (10, 11, 17, 19)": "ANDY",
    "Route 12 (12)": "Route 12",
}

JSON_FILE = "group_map.json"


# =========================================
# 2. 加载 / 保存 用户新增的 映射
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
            drivers = []
            for d in v:
                try:
                    drivers.append(int(d))
                except:
                    continue
            result[str(k)] = list(set(drivers))
        return result
    return {}


def save_group_map(group_map):
    serializable = {str(k): list(map(int, v)) for k, v in group_map.items()}
    with open(JSON_FILE, "w") as f:
        json.dump(serializable, f, indent=4)


SAVED_MAP = load_saved_map()

# 合并默认映射和新增映射
GROUP_MAP = DEFAULT_GROUP_MAP.copy()
for g, drivers in SAVED_MAP.items():
    if g in GROUP_MAP:
        GROUP_MAP[g] = list(set(GROUP_MAP[g] + drivers))
    else:
        GROUP_MAP[g] = drivers


# ==============================
# 3. 侧边栏 新增 driver → 分类
# ==============================
st.sidebar.subheader("添加新的 Driver → 分类")

new_driver = st.sidebar.text_input("Driver ID（例如 5201554）")
selected_display = st.sidebar.selectbox("分类", GROUP_OPTIONS)

if st.sidebar.button("保存映射"):
    if new_driver:
        try:
            driver_id = int(new_driver)
        except:
            st.sidebar.error("Driver ID 必须是数字")
        else:
            internal_group = DISPLAY_TO_INTERNAL[selected_display]

            # 更新 runtime map
            GROUP_MAP[internal_group].append(driver_id)
            GROUP_MAP[internal_group] = list(set(GROUP_MAP[internal_group]))

            # 更新本地文件 map
            SAVED_MAP.setdefault(internal_group, [])
            SAVED_MAP[internal_group].append(driver_id)
            SAVED_MAP[internal_group] = list(set(SAVED_MAP[internal_group]))

            save_group_map(SAVED_MAP)

            st.sidebar.success(f"已保存：Driver {driver_id} → {internal_group}")
    else:
        st.sidebar.error("请先填写 Driver ID")


# ==============================
# 4. 阈值设置
# ==============================
st.sidebar.markdown("---")
st.sidebar.header("异常司机阈值")

low_completion_threshold = st.sidebar.slider("完成率低于多少算“比较低”？(%)",
                                             0, 100, 80, step=5)
inactive_hours_threshold = st.sidebar.slider("Inactive 时间大于多少小时算异常？",
                                             1.0, 10.0, 3.0, step=0.5)


# ==============================
# 5. 上传 Excel/CSV
# ==============================
uploaded_file = st.file_uploader("上传 Delivery Monitoring 导出的 Excel（xlsx/csv）",
                                 type=["xlsx", "csv"])

if uploaded_file is None:
    st.info("请上传 driverEfficiency 文件")
    st.stop()

df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith(".xlsx") else pd.read_csv(uploaded_file)
df.columns = [str(c).strip() for c in df.columns]


# ==============================
# 6. 自动识别关键列
# ==============================
driver_col = [c for c in df.columns if "driver" in c.lower()][0]
tbd_col = [c for c in df.columns if "/" in str(df[c].iloc[0])][0]
comp_col = [c for c in df.columns if "completion" in c.lower()][0]
inactive_col = [c for c in df.columns if "inactive" in c.lower()][0]

# ==============================
# 7. 解析字段
# ==============================
split = df[tbd_col].astype(str).str.split("/", expand=True)
df["to_be"] = pd.to_numeric(split[0], errors="coerce").fillna(0)
df["total"] = pd.to_numeric(split[1], errors="coerce").fillna(0)
df["delivered"] = df["total"] - df["to_be"]

df["completion"] = pd.to_numeric(df[comp_col].str.rstrip("%"), errors="coerce")

def time_to_hours(x):
    try:
        h, m, s = map(int, str(x).split(":"))
        return h + m/60 + s/3600
    except:
        return np.nan

df["inactive_hours"] = df[inactive_col].apply(time_to_hours)

def assign_group(driver):
    d = int(driver)
    for g, drivers in GROUP_MAP.items():
        if d in drivers:
            return g
    return "UNASSIGNED"

df["group"] = df[driver_col].apply(assign_group)

# ==============================
# 8. 汇总到司机
# ==============================
driver_group = (
    df.groupby([driver_col, "group"], as_index=False)
    .agg(
        completion_rate_pct=("completion", "mean"),
        delivered=("delivered", "sum"),
        to_be=("to_be", "sum"),
        total=("total", "sum"),
        inactive_hours=("inactive_hours", "max"),
    )
)

def hours_to_hms(h):
    if pd.isna(h): return "N/A"
    sec = int(h * 3600)
    return f"{sec//3600}h {(sec%3600)//60}m {sec%60}s"

driver_group["inactive_time_str"] = driver_group["inactive_hours"].apply(hours_to_hms)


# ==============================
# 9. 总体指标
# ==============================
st.subheader("总体完成情况")
c1, c2, c3 = st.columns(3)

overall_completion = driver_group["delivered"].sum() / max(driver_group["total"].sum(), 1)

c1.metric("Overall Completion Rate", f"{overall_completion*100:.1f}%")
c2.metric("Total Packages", int(driver_group["total"].sum()))
c3.metric("Remaining Packages", int(driver_group["to_be"].sum()))


# ==============================
# 10. 单图：按分类着色的完成率图（唯一需要的图）
# ==============================
st.subheader("按司机完成率（按分类着色）")

chart_group = (
    alt.Chart(driver_group)
    .mark_bar()
    .encode(
        x=alt.X("completion_rate_pct:Q", title="Completion Rate (%)"),
        y=alt.Y(f"{driver_col}:N", sort="-x", title="Driver ID"),
        color=alt.Color("group:N", title="Group"),  # 🔥 保证不显示 display 名称
        tooltip=[
            alt.Tooltip(driver_col, title="Driver ID"),
            alt.Tooltip("group:N", title="Group"),
            alt.Tooltip("completion_rate_pct:Q", title="Completion (%)"),
            alt.Tooltip("inactive_time_str:N", title="Inactive"),
        ],
    )
    .properties(height=600)
)

st.altair_chart(chart_group, use_container_width=True)


# ==============================
# 11. 异常司机表
# ==============================
st.subheader("异常司机（Inactive 过长 & 完成率偏低）")

flag = (driver_group["inactive_hours"] >= inactive_hours_threshold) & \
       (driver_group["completion_rate_pct"] < low_completion_threshold)

bad = driver_group[flag]

if bad.empty:
    st.success("没有异常司机！")
else:
    st.warning(f"共发现 {len(bad)} 名异常司机：")
    st.dataframe(
        bad[[driver_col, "group", "completion_rate_pct",
             "inactive_time_str", "delivered", "to_be", "total"]],
        use_container_width=True
    )
