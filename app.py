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

# =========================================================
# 1. 统一标准：只使用下面这几个分组名字（带路线号）
# =========================================================
DISPLAY_GROUPS = [
    "DING DONG (3, 6)",
    "SPEEDY (2, 9, 20)",
    "ANDY (10, 17, 19)",   # 去掉 11
    "JESSICA (11)",        # 新增单独的 Route 11
    "ULTIMILE (12)",       # Route 12 改名
]

# 有些旧版本 json 里可能存的是不带路线号的名字，这里做一个映射转换
INTERNAL_TO_DISPLAY = {
    "DING DONG": "DING DONG (3, 6)",
    "SPEEDY": "SPEEDY (2, 9, 20)",
    "ANDY": "ANDY (10, 17, 19)",
    "Route 12": "ULTIMILE (12)",          # 旧名映射到新名
    "ULTIMILE": "ULTIMILE (12)",
    "JESSICA": "JESSICA (11)",

    # 兼容更老的带括号老名字
    "ANDY (10, 11, 17, 19)": "ANDY (10, 17, 19)",
    "Route 12 (12)": "ULTIMILE (12)",
}

# 默认：分组名（带路线号） → 司机列表
DEFAULT_GROUP_MAP = {
    "DING DONG (3, 6)": [
        # Route 3
        60911, 93787, 95091, 96528, 5003395, 5005937, 5006711,
        5200583, 5201764, 5202196, 5202457, 5205698, 5207998, 5217073,
        # Route 6
        31976, 54274, 94870, 5002004, 5005943, 5009726, 5205299,
    ],
    "SPEEDY (2, 9, 20)": [
        # Route 2
        20025, 20032, 20038, 20041, 44776, 46353, 94361, 5004645, 5006742,
        # Route 9
        79638, 86494, 86495, 88016, 5203839,
        # Route 20
        86492, 87043, 5000938,
    ],
    "ANDY (10, 17, 19)": [
        # Route 10
        11150, 11167, 39871, 44640, 5216349,
        # Route 17
        11154, 5205901,
        # Route 19
        37621, 37626, 5007017, 5209368, 5215916,
    ],
    "JESSICA (11)": [
        # Route 11 单独出来
        44650,
    ],
    "ULTIMILE (12)": [
        89828, 5201554, 5201598, 5201602, 5207482,
        5209676, 5210936, 5216145, 5216152,
    ],
}

JSON_FILE = "group_map.json"


# =========================================================
# 2. 加载 / 保存 自定义分组映射
# =========================================================
def load_saved_map():
    """
    从本地 json 读取你自己添加过的 driver → group 映射。
    兼容旧版本（key 是 DING DONG/SPEEDY 这种不带路线号的，
    以及更早的 ANDY (10, 11, 17, 19) / Route 12 (12) 等）。
    """
    if not os.path.exists(JSON_FILE):
        return {}

    try:
        with open(JSON_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        return {}

    result = {}
    for raw_key, drivers in data.items():
        # 把旧 key 转换成新 key（带路线号/新名字）
        display_key = INTERNAL_TO_DISPLAY.get(raw_key, raw_key)
        clean_drivers = []
        for d in drivers:
            try:
                clean_drivers.append(int(d))
            except Exception:
                continue
        if display_key in result:
            result[display_key] = list(set(result[display_key] + clean_drivers))
        else:
            result[display_key] = list(set(clean_drivers))
    return result


def save_group_map(group_map):
    """
    把当前分组映射写入 json。
    直接用“带路线号”的名字做 key。
    """
    serializable = {str(k): [int(d) for d in v] for k, v in group_map.items()}
    with open(JSON_FILE, "w") as f:
        json.dump(serializable, f, indent=4)


SAVED_MAP = load_saved_map()

# 合并默认映射和用户映射
GROUP_MAP = DEFAULT_GROUP_MAP.copy()
for g, drivers in SAVED_MAP.items():
    if g in GROUP_MAP:
        GROUP_MAP[g] = list(set(GROUP_MAP[g] + drivers))
    else:
        GROUP_MAP[g] = list(set(drivers))


# =========================================================
# 3. 侧边栏：新增 Driver → 分组
# =========================================================
st.sidebar.subheader("添加新的 Driver → 分类")

new_driver = st.sidebar.text_input("Driver ID（例如 5201554）")
selected_group_display = st.sidebar.selectbox("分类", DISPLAY_GROUPS)

if st.sidebar.button("保存映射"):
    if not new_driver:
        st.sidebar.error("请先填写 Driver ID")
    else:
        try:
            driver_id = int(new_driver)
        except ValueError:
            st.sidebar.error("Driver ID 必须是数字")
        else:
            group_name = selected_group_display  # 目标分组

            # 1) 先从所有其他分组里移除这个 driver_id
            for g, drivers in GROUP_MAP.items():
                if g != group_name and driver_id in drivers:
                    drivers.remove(driver_id)

            for g, drivers in list(SAVED_MAP.items()):
                if g != group_name and driver_id in drivers:
                    drivers.remove(driver_id)
                # 如果某个分组在 SAVED_MAP 里变成空列表，可以顺便删掉
                if g != group_name and not drivers:
                    del SAVED_MAP[g]

            # 2) 再加到目标分组
            GROUP_MAP.setdefault(group_name, [])
            if driver_id not in GROUP_MAP[group_name]:
                GROUP_MAP[group_name].append(driver_id)

            SAVED_MAP.setdefault(group_name, [])
            if driver_id not in SAVED_MAP[group_name]:
                SAVED_MAP[group_name].append(driver_id)

            # 3) 保存到 json
            save_group_map(SAVED_MAP)
            st.sidebar.success(f"已更新：Driver {driver_id} → {group_name}（已从其他分组移除）")

# =========================================================
# 4. 异常阈值设置
# =========================================================
st.sidebar.markdown("---")
st.sidebar.header("异常司机阈值")

low_completion_threshold = st.sidebar.slider(
    "完成率低于多少算“比较低”？(%)",
    min_value=0, max_value=100, value=80, step=5,
)

inactive_hours_threshold = st.sidebar.slider(
    "Inactive 时间大于多少小时算异常？",
    min_value=1.0, max_value=10.0, value=3.0, step=0.5,
)

# =========================================================
# 5. 上传 Excel/CSV
# =========================================================
uploaded_file = st.file_uploader(
    "上传 Delivery Monitoring 导出的 Excel（xlsx/csv）",
    type=["xlsx", "csv"],
)

if uploaded_file is None:
    st.info("请上传 driverEfficiency 之类的导出文件。")
    st.stop()

if uploaded_file.name.endswith(".csv"):
    df = pd.read_csv(uploaded_file)
else:
    df = pd.read_excel(uploaded_file)

df.columns = [str(c).strip() for c in df.columns]

# =========================================================
# 6. 自动识别关键列
# =========================================================
driver_candidates = [c for c in df.columns if "driver" in c.lower()]
driver_col = driver_candidates[0] if driver_candidates else df.columns[0]

tbd_candidates = [c for c in df.columns if "to be" in c.lower() or "delivered/total" in c.lower()]
tbd_col = tbd_candidates[0] if tbd_candidates else df.columns[-5]

comp_candidates = [c for c in df.columns if "completion" in c.lower()]
comp_col = comp_candidates[0] if comp_candidates else df.columns[-4]

inactive_candidates = [c for c in df.columns if "inactive" in c.lower()]
inactive_col = inactive_candidates[0] if inactive_candidates else df.columns[-1]

st.subheader("原始数据预览")
st.write(
    f"识别的列：Driver = `{driver_col}`, ToBe/Total = `{tbd_col}`, "
    f"Completion = `{comp_col}`, Inactive = `{inactive_col}`"
)
st.dataframe(df.head(), use_container_width=True)

# =========================================================
# 7. 字段解析
# =========================================================
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

# 7.4 把司机映射到分组（用带路线号的名字）
def assign_group(driver):
    try:
        d = int(driver)
    except Exception:
        return "UNASSIGNED"
    for group_name, drivers in GROUP_MAP.items():
        if d in drivers:
            return group_name
    return "UNASSIGNED"


df["group"] = df[driver_col].apply(assign_group)

# =========================================================
# 8. 汇总到司机层级
# =========================================================
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
    if pd.isna(h):
        return "N/A"
    if h < 0:
        h = 0
    total_seconds = int(round(h * 3600))
    H = total_seconds // 3600
    M = (total_seconds % 3600) // 60
    S = total_seconds % 60
    return f"{H}h {M}m {S}s"


driver_group["inactive_time_str"] = driver_group["inactive_hours"].apply(hours_to_hms)

# =========================================================
# 9. 总体完成情况
# =========================================================
st.subheader("总体完成情况")
c1, c2, c3 = st.columns(3)

if driver_group["total"].sum() > 0:
    overall_completion = driver_group["delivered"].sum() / driver_group["total"].sum()
else:
    overall_completion = 0.0

c1.metric("Overall Completion Rate", f"{overall_completion * 100:.1f}%")
c2.metric("Total Packages", int(driver_group["total"].sum()))
c3.metric("Remaining Packages", int(driver_group["to_be"].sum()))

# =========================================================
# 10. 图表：按分类着色的完成率
# =========================================================
st.subheader("按司机完成率（按分类着色）")

chart_group = (
    alt.Chart(driver_group)
    .mark_bar()
    .encode(
        x=alt.X("completion_rate_pct:Q", title="Completion Rate (%)"),
        y=alt.Y(f"{driver_col}:N", sort="-x", title="Driver ID"),
        color=alt.Color("group:N", title="Group"),
        tooltip=[
            alt.Tooltip(driver_col, title="Driver ID"),
            alt.Tooltip("group:N", title="Group"),
            alt.Tooltip("completion_rate_pct:Q", title="Completion Rate"),
            alt.Tooltip("inactive_time_str:N", title="Inactive Time"),
        ],
    )
    .properties(height=600)
)

st.altair_chart(chart_group, use_container_width=True)

# =========================================================
# 11. 异常司机列表
# =========================================================
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
        driver_col, "group",
        "completion_rate_pct", "inactive_time_str",
        "delivered", "to_be", "total",
    ]
    st.dataframe(
        flagged[display_cols].sort_values("completion_rate_pct"),
        use_container_width=True,
    )
