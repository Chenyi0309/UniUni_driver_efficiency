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
# 0. Team ID → 公司（最终统一规则）
# =========================================================
TEAM_ID_TO_GROUP = {
    849: "ANDY (10, 12, 17, 19)",
    853: "ANDY (10, 12, 17, 19)",
    600: "DING DONG (3, 6)",
    369: "SPEEDY (2, 9, 20)",
    1337: "JESSICA (11)",
}

DISPLAY_GROUPS = {
    "ANDY (Team 849, 853 | Routes 10, 12, 17, 19)": [849, 853],
    "DING DONG (Team 600 | Routes 3, 6)": [600],
    "SPEEDY (Team 369 | Routes 2, 9, 20)": [369],
    "JESSICA (Team 1337 | Route 11)": [1337],
}

JSON_FILE = "driver_team_map.json"

# =========================================================
# 1. 加载 / 保存 Driver → Team ID
# =========================================================
def load_saved_map():
    if not os.path.exists(JSON_FILE):
        return {}
    try:
        with open(JSON_FILE, "r") as f:
            data = json.load(f)
        return {int(k): list(map(int, v)) for k, v in data.items()}
    except Exception:
        return {}

def save_group_map(group_map):
    serializable = {str(k): v for k, v in group_map.items()}
    with open(JSON_FILE, "w") as f:
        json.dump(serializable, f, indent=4)

SAVED_MAP = load_saved_map()

# =========================================================
# 2. Sidebar：批量添加 Driver → Team
# =========================================================
st.sidebar.subheader("添加新的 Driver → 分类")

raw_driver_input = st.sidebar.text_input(
    "Driver ID（可输入多个，用逗号或空格隔开）"
)

selected_group_label = st.sidebar.selectbox(
    "分类（公司 / Team ID）",
    list(DISPLAY_GROUPS.keys())
)

if st.sidebar.button("保存映射"):
    if not raw_driver_input.strip():
        st.sidebar.error("请至少输入一个 Driver ID")
        st.stop()

    raw_ids = raw_driver_input.replace(",", " ").split()
    try:
        driver_ids = [int(x) for x in raw_ids]
    except ValueError:
        st.sidebar.error("Driver ID 必须是数字")
        st.stop()

    target_team_id = DISPLAY_GROUPS[selected_group_label][0]

    # 覆盖旧记录：先移除
    for team_id in list(SAVED_MAP.keys()):
        SAVED_MAP[team_id] = [
            d for d in SAVED_MAP[team_id] if d not in driver_ids
        ]
        if not SAVED_MAP[team_id]:
            del SAVED_MAP[team_id]

    # 加入新 team
    SAVED_MAP.setdefault(target_team_id, [])
    for d in driver_ids:
        if d not in SAVED_MAP[target_team_id]:
            SAVED_MAP[target_team_id].append(d)

    save_group_map(SAVED_MAP)

    st.sidebar.success(
        f"已保存 {len(driver_ids)} 个司机 → Team {target_team_id}"
    )

# =========================================================
# 3. 异常阈值
# =========================================================
st.sidebar.markdown("---")
st.sidebar.header("异常司机阈值")

low_completion_threshold = st.sidebar.slider(
    "完成率低于多少算异常 (%)", 0, 100, 80, 5
)

inactive_hours_threshold = st.sidebar.slider(
    "Inactive 时间大于多少小时算异常", 1.0, 24.0, 3.0, 0.5
)

# =========================================================
# 4. 上传 Excel
# =========================================================
uploaded_file = st.file_uploader(
    "上传 Delivery Monitoring 导出的 Excel / CSV",
    type=["xlsx", "csv"],
)

if uploaded_file is None:
    st.info("请上传文件")
    st.stop()

if uploaded_file.name.endswith(".csv"):
    df = pd.read_csv(uploaded_file)
else:
    df = pd.read_excel(uploaded_file)

df.columns = [str(c).strip() for c in df.columns]

# =========================================================
# 5. 自动识别列
# =========================================================
driver_col = next((c for c in df.columns if "driver" in c.lower()), df.columns[0])
tbd_col = next((c for c in df.columns if "/" in c.lower()), df.columns[-5])
comp_col = next((c for c in df.columns if "completion" in c.lower()), df.columns[-4])
inactive_col = next((c for c in df.columns if "inactive" in c.lower()), df.columns[-1])

# =========================================================
# 6. 字段解析
# =========================================================
split = df[tbd_col].astype(str).str.split("/", expand=True)
df["to_be"] = pd.to_numeric(split[0], errors="coerce").fillna(0)
df["total"] = pd.to_numeric(split[1], errors="coerce").fillna(0)
df["delivered"] = df["total"] - df["to_be"]

df["completion"] = (
    df[comp_col].astype(str).str.rstrip("%").replace("", np.nan)
)
df["completion"] = pd.to_numeric(df["completion"], errors="coerce")

def time_to_hours(x):
    try:
        h, m, s = map(int, str(x).split(":"))
        return h + m / 60 + s / 3600
    except Exception:
        return np.nan

df["inactive_hours"] = df[inactive_col].apply(time_to_hours)

# =========================================================
# 7. Driver → Team → Group
# =========================================================
def assign_group(driver_id):
    try:
        d = int(driver_id)
    except Exception:
        return "UNASSIGNED"

    for team_id, drivers in SAVED_MAP.items():
        if d in drivers:
            return TEAM_ID_TO_GROUP.get(team_id, "UNASSIGNED")

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
    total_seconds = int(h * 3600)
    return f"{total_seconds//3600}h {(total_seconds%3600)//60}m"

driver_group["inactive_time_str"] = driver_group["inactive_hours"].apply(hours_to_hms)

# =========================================================
# 9. 图表
# =========================================================
st.subheader("按司机完成率（按公司着色）")

chart = (
    alt.Chart(driver_group)
    .mark_bar()
    .encode(
        x=alt.X("completion_rate_pct:Q", title="Completion Rate (%)"),
        y=alt.Y(f"{driver_col}:N", sort="-x"),
        color="group:N",
        tooltip=[
            driver_col,
            "group",
            "completion_rate_pct",
            "inactive_time_str",
        ],
    )
    .properties(height=600)
)

st.altair_chart(chart, use_container_width=True)

# =========================================================
# 10. 异常司机
# =========================================================
st.subheader("异常司机")

mask = (
    (driver_group["completion_rate_pct"] < low_completion_threshold)
    & (driver_group["inactive_hours"] >= inactive_hours_threshold)
)

flagged = driver_group[mask]

if flagged.empty:
    st.success("暂无异常司机")
else:
    st.dataframe(flagged, use_container_width=True)
