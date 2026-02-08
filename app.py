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
# 0) Team ID → Group（你最新的最终规则）
# =========================================================
TEAM_ID_TO_GROUP = {
    849: "ANDY (10, 17, 19)",
    853: "ULTIMILE (12)",
    600: "DING DONG (3, 6)",
    369: "SPEEDY (2, 9, 20)",
    1337: "TJ (11)",
}

# Sidebar 下拉显示（公司 + Team ID + Route）
DISPLAY_GROUPS = {
    "ANDY (Team 849 | Routes 10, 17, 19)": [849],
    "ULTIMILE (Team 853 | Route 12)": [853],
    "DING DONG (Team 600 | Routes 3, 6)": [600],
    "SPEEDY (Team 369 | Routes 2, 9, 20)": [369],
    "TJ (Team 1337 | Route 11)": [1337],
}

JSON_FILE = "driver_team_map.json"

# =========================================================
# 1) 加载 / 保存：Team ID → [Driver IDs]
# =========================================================
def load_saved_map():
    if not os.path.exists(JSON_FILE):
        return {}
    try:
        with open(JSON_FILE, "r") as f:
            data = json.load(f)
        # json: { "849": [11155, ...], "600": [...] }
        return {int(k): [int(x) for x in v] for k, v in data.items()}
    except Exception:
        return {}

def save_group_map(group_map):
    serializable = {str(k): [int(x) for x in v] for k, v in group_map.items()}
    with open(JSON_FILE, "w") as f:
        json.dump(serializable, f, indent=4)

SAVED_MAP = load_saved_map()

# =========================================================
# 2) Sidebar：批量添加 Driver → Team（支持覆盖）
# =========================================================
st.sidebar.subheader("添加新的 Driver → 分类（可批量）")

raw_driver_input = st.sidebar.text_input(
    "Driver ID（可输入多个，用逗号或空格隔开）",
    placeholder="例如：11155, 11160 11165",
)

selected_group_label = st.sidebar.selectbox(
    "分类（公司 / Team ID）",
    list(DISPLAY_GROUPS.keys()),
)

if st.sidebar.button("保存映射"):
    if not raw_driver_input.strip():
        st.sidebar.error("请至少输入一个 Driver ID")
        st.stop()

    # 解析 Driver IDs
    raw_ids = raw_driver_input.replace(",", " ").split()
    try:
        driver_ids = [int(x) for x in raw_ids]
    except ValueError:
        st.sidebar.error("Driver ID 必须是数字（用逗号或空格分隔）")
        st.stop()

    target_team_id = DISPLAY_GROUPS[selected_group_label][0]

    # 覆盖旧记录：先从所有 team 中移除这些司机
    for team_id in list(SAVED_MAP.keys()):
        SAVED_MAP[team_id] = [d for d in SAVED_MAP[team_id] if d not in driver_ids]
        if not SAVED_MAP[team_id]:
            del SAVED_MAP[team_id]

    # 加入目标 team
    SAVED_MAP.setdefault(target_team_id, [])
    for d in driver_ids:
        if d not in SAVED_MAP[target_team_id]:
            SAVED_MAP[target_team_id].append(d)

    save_group_map(SAVED_MAP)
    st.sidebar.success(f"已保存 {len(driver_ids)} 个司机 → Team {target_team_id}")

st.sidebar.markdown("---")
st.sidebar.caption("提示：输错了直接再输一次并保存，会自动覆盖到新 Team。")

# =========================================================
# 3) 异常阈值
# =========================================================
st.sidebar.header("异常司机阈值")

low_completion_threshold = st.sidebar.slider(
    "完成率低于多少算异常 (%)",
    min_value=0, max_value=100, value=80, step=5
)

inactive_hours_threshold = st.sidebar.slider(
    "Inactive 时间大于多少小时算异常",
    min_value=0.5, max_value=24.0, value=3.0, step=0.5
)

# =========================================================
# 4) 上传 Excel / CSV
# =========================================================
uploaded_file = st.file_uploader(
    "上传 Delivery Monitoring 导出的 Excel（xlsx）或 CSV",
    type=["xlsx", "csv"],
)

if uploaded_file is None:
    st.info("请先上传文件。")
    st.stop()

if uploaded_file.name.lower().endswith(".csv"):
    df = pd.read_csv(uploaded_file)
else:
    df = pd.read_excel(uploaded_file)

df.columns = [str(c).strip() for c in df.columns]

# =========================================================
# 5) 自动识别关键列（更稳健一点）
# =========================================================
def pick_col(candidates, fallback_idx=None):
    return candidates[0] if candidates else (df.columns[fallback_idx] if fallback_idx is not None else df.columns[0])

driver_candidates = [c for c in df.columns if "driver" in c.lower()]
driver_col = pick_col(driver_candidates, 0)

tbd_candidates = [c for c in df.columns if ("to be" in c.lower()) or ("delivered/total" in c.lower()) or ("tobe/total" in c.lower())]
tbd_col = pick_col(tbd_candidates, -5)

comp_candidates = [c for c in df.columns if "completion" in c.lower()]
comp_col = pick_col(comp_candidates, -4)

inactive_candidates = [c for c in df.columns if "inactive" in c.lower()]
inactive_col = pick_col(inactive_candidates, -1)

st.subheader("原始数据预览")
st.write(
    f"识别到的列：Driver=`{driver_col}`，ToBe/Total=`{tbd_col}`，Completion=`{comp_col}`，Inactive=`{inactive_col}`"
)
st.dataframe(df.head(20), use_container_width=True)

# =========================================================
# 6) 字段解析
# =========================================================
# 6.1 To be delivered / Total
split = df[tbd_col].astype(str).str.split("/", expand=True)
df["to_be"] = pd.to_numeric(split[0], errors="coerce").fillna(0).astype(int)
df["total"] = pd.to_numeric(split[1], errors="coerce").fillna(0).astype(int)
df["delivered"] = (df["total"] - df["to_be"]).clip(lower=0)

# 6.2 Completion
df["completion"] = (
    df[comp_col].astype(str).str.strip().str.rstrip("%").replace("", np.nan)
)
df["completion"] = pd.to_numeric(df["completion"], errors="coerce")

# 6.3 Inactive -> hours
def time_to_hours(x):
    s = str(x).strip()
    if ":" not in s:
        return np.nan
    parts = s.split(":")
    if len(parts) != 3:
        return np.nan
    try:
        h, m, sec = map(int, parts)
        return h + m / 60 + sec / 3600
    except Exception:
        return np.nan

df["inactive_hours"] = df[inactive_col].apply(time_to_hours)

# =========================================================
# 7) Driver → Team → Group（核心）
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
# 8) 汇总到司机层级
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
# 9) 总体完成情况
# =========================================================
st.subheader("总体完成情况")
c1, c2, c3 = st.columns(3)

total_pkg = int(driver_group["total"].sum())
delivered_pkg = int(driver_group["delivered"].sum())
remaining_pkg = int(driver_group["to_be"].sum())

overall_completion = (delivered_pkg / total_pkg) if total_pkg > 0 else 0.0
c1.metric("Overall Completion Rate", f"{overall_completion * 100:.1f}%")
c2.metric("Total Packages", total_pkg)
c3.metric("Remaining Packages", remaining_pkg)

# =========================================================
# 10) 图表：按公司着色的完成率
# =========================================================
st.subheader("按司机完成率（按公司着色）")

chart = (
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
              alt.Tooltip("delivered:Q", title="Delivered"),
              alt.Tooltip("to_be:Q", title="Remaining"),
              alt.Tooltip("total:Q", title="Total"),
          ],
      )
      .properties(height=650)
)

st.altair_chart(chart, use_container_width=True)

# =========================================================
# 11) 异常司机
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

# =========================================================
# 12) 可选：提示未被映射的司机
# =========================================================
unassigned = driver_group[driver_group["group"] == "UNASSIGNED"]
if not unassigned.empty:
    st.info(f"提示：有 {len(unassigned)} 个司机未映射到任何 Team/Group（显示为 UNASSIGNED）。")
    st.dataframe(unassigned[[driver_col, "completion_rate_pct", "inactive_time_str", "delivered", "to_be", "total"]],
                 use_container_width=True)
