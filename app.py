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
# 0) 配置
# =========================================================
TEAM_ID_TO_GROUP = {
    849: "ANDY (10, 17, 19)",
    853: "ULTIMILE (12)",
    600: "DING DONG (3, 6)",
    369: "SPEEDY (2, 9, 20)",
    1337: "TJ (11)",
}

DISPLAY_GROUPS = {
    "ANDY (Team 849 | Routes 10, 17, 19)": [849],
    "ULTIMILE (Team 853 | Route 12)": [853],
    "DING DONG (Team 600 | Routes 3, 6)": [600],
    "SPEEDY (Team 369 | Routes 2, 9, 20)": [369],
    "TJ (Team 1337 | Route 11)": [1337],
}

# Google Sheet: DSP 这一页
GOOGLE_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/1NhgYseeXp20uYjopelAsQPM2yZDvJr59pDLpJZNPQyg/edit?usp=sharing"
)

# DSP 名称 -> Team ID
DSP_NAME_TO_TEAM_ID = {
    "andy": 849,
    "dingdong": 600,
    "ding dong": 600,
    "speedy": 369,
    "tj": 1337,
    "ultimile": 853,
}

JSON_FILE = "driver_team_map.json"


# =========================================================
# 1) 工具函数
# =========================================================
def normalize_dsp_name(x):
    if pd.isna(x):
        return ""
    return str(x).strip().lower()


def pick_col(df, possible_names, fallback=None):
    """
    在 DataFrame 中按候选列名查找列。
    """
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for name in possible_names:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return fallback


def invert_driver_to_team_map(driver_to_team):
    """
    {driver_id: team_id} -> {team_id: [driver_ids]}
    """
    result = {}
    for driver_id, team_id in driver_to_team.items():
        result.setdefault(int(team_id), []).append(int(driver_id))
    for k in result:
        result[k] = sorted(list(set(result[k])))
    return result


# =========================================================
# 2) 读取 Google Sheet（主数据源）
# =========================================================
@st.cache_data(ttl=300)
def load_sheet_driver_map():
    """
    从 Google Sheet 的 DSP sheet 读取：
    司机号 + DSP 名称
    然后映射成 driver_id -> team_id

    要求：
    - Sheet 可访问（至少链接可查看）
    - DSP sheet 中有 “司机号” 和 “DSP” 两列
    """
    try:
        sheet_df = pd.read_csv(GOOGLE_SHEET_CSV_URL)
    except Exception as e:
        return {}, f"无法读取 Google Sheet：{e}"

    sheet_df.columns = [str(c).strip() for c in sheet_df.columns]

    driver_col = pick_col(sheet_df, ["司机号", "driver id", "driver", "driver_id"])
    dsp_col = pick_col(sheet_df, ["dsp", "DSP"])

    if driver_col is None or dsp_col is None:
        return {}, "Google Sheet 的 DSP 页中没有找到“司机号”或“DSP”列。"

    temp = sheet_df[[driver_col, dsp_col]].copy()
    temp[driver_col] = pd.to_numeric(temp[driver_col], errors="coerce")
    temp = temp.dropna(subset=[driver_col])

    temp["team_id"] = temp[dsp_col].apply(
        lambda x: DSP_NAME_TO_TEAM_ID.get(normalize_dsp_name(x), np.nan)
    )
    temp = temp.dropna(subset=["team_id"])

    driver_to_team = {}
    for _, row in temp.iterrows():
        driver_id = int(row[driver_col])
        team_id = int(row["team_id"])
        driver_to_team[driver_id] = team_id

    return driver_to_team, None


# =========================================================
# 3) 读取 / 保存 本地补充映射（长期补充层）
# =========================================================
def load_local_driver_map():
    """
    本地 JSON 存的是 driver_id -> team_id
    """
    if not os.path.exists(JSON_FILE):
        return {}

    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        result = {}
        for k, v in data.items():
            try:
                result[int(k)] = int(v)
            except Exception:
                continue
        return result
    except Exception:
        return {}


def save_local_driver_map(driver_map):
    serializable = {str(k): int(v) for k, v in driver_map.items()}
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=4, ensure_ascii=False)


SHEET_DRIVER_MAP, SHEET_ERROR = load_sheet_driver_map()
LOCAL_DRIVER_MAP = load_local_driver_map()

# 最终规则：
# 1) 先用本地补充映射（可覆盖）
# 2) 再用 Google Sheet 主表
FINAL_DRIVER_MAP = SHEET_DRIVER_MAP.copy()
FINAL_DRIVER_MAP.update(LOCAL_DRIVER_MAP)

FINAL_TEAM_MAP = invert_driver_to_team_map(FINAL_DRIVER_MAP)


# =========================================================
# 4) Sidebar：批量添加 Driver → Team（保存到本地 JSON）
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

    raw_ids = raw_driver_input.replace(",", " ").split()
    try:
        driver_ids = [int(x) for x in raw_ids]
    except ValueError:
        st.sidebar.error("Driver ID 必须是数字（用逗号或空格分隔）")
        st.stop()

    target_team_id = DISPLAY_GROUPS[selected_group_label][0]

    # 更新本地补充映射：driver_id -> team_id
    for d in driver_ids:
        LOCAL_DRIVER_MAP[int(d)] = int(target_team_id)

    save_local_driver_map(LOCAL_DRIVER_MAP)

    st.sidebar.success(
        f"已保存 {len(driver_ids)} 个司机到本地补充映射 → Team {target_team_id}"
    )
    st.sidebar.info("刷新后会优先使用你刚刚保存的本地映射。")

st.sidebar.markdown("---")
st.sidebar.caption("说明：Google Sheet 是主表；你在这里新增的司机会保存到本地 JSON，并优先覆盖主表。")

if SHEET_ERROR:
    st.sidebar.warning(SHEET_ERROR)
else:
    st.sidebar.success(f"已读取 Google Sheet 主表司机数：{len(SHEET_DRIVER_MAP)}")

st.sidebar.write(f"本地补充司机数：{len(LOCAL_DRIVER_MAP)}")


# =========================================================
# 5) 异常阈值
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
# 6) 上传 Excel / CSV
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
# 7) 自动识别关键列
# =========================================================
def pick_runtime_col(candidates, fallback_idx=None):
    return candidates[0] if candidates else (
        df.columns[fallback_idx] if fallback_idx is not None else df.columns[0]
    )

driver_candidates = [c for c in df.columns if "driver" in c.lower()]
driver_col = pick_runtime_col(driver_candidates, 0)

tbd_candidates = [
    c for c in df.columns
    if ("to be" in c.lower()) or ("delivered/total" in c.lower()) or ("tobe/total" in c.lower())
]
tbd_col = pick_runtime_col(tbd_candidates, -5)

comp_candidates = [c for c in df.columns if "completion" in c.lower()]
comp_col = pick_runtime_col(comp_candidates, -4)

inactive_candidates = [c for c in df.columns if "inactive" in c.lower()]
inactive_col = pick_runtime_col(inactive_candidates, -1)

st.subheader("原始数据预览")
st.write(
    f"识别到的列：Driver=`{driver_col}`，ToBe/Total=`{tbd_col}`，Completion=`{comp_col}`，Inactive=`{inactive_col}`"
)
st.dataframe(df.head(20), use_container_width=True)


# =========================================================
# 8) 字段解析
# =========================================================
split = df[tbd_col].astype(str).str.split("/", expand=True)
df["to_be"] = pd.to_numeric(split[0], errors="coerce").fillna(0).astype(int)
df["total"] = pd.to_numeric(split[1], errors="coerce").fillna(0).astype(int)
df["delivered"] = (df["total"] - df["to_be"]).clip(lower=0)

df["completion"] = (
    df[comp_col].astype(str).str.strip().str.rstrip("%").replace("", np.nan)
)
df["completion"] = pd.to_numeric(df["completion"], errors="coerce")


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
# 9) Driver → Team → Group（核心）
# =========================================================
def assign_group(driver_id):
    try:
        d = int(driver_id)
    except Exception:
        return "UNASSIGNED"

    team_id = FINAL_DRIVER_MAP.get(d)
    if team_id is None:
        return "UNASSIGNED"

    return TEAM_ID_TO_GROUP.get(team_id, "UNASSIGNED")


df["group"] = df[driver_col].apply(assign_group)


# =========================================================
# 10) 汇总到司机层级
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
# 11) 总体完成情况
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
# 12) 图表：按公司着色的完成率
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
# 13) 异常司机
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
# 14) 提示未映射司机
# =========================================================
unassigned = driver_group[driver_group["group"] == "UNASSIGNED"]
if not unassigned.empty:
    st.info(f"提示：有 {len(unassigned)} 个司机未映射到任何 Team/Group（显示为 UNASSIGNED）。")
    st.dataframe(
        unassigned[
            [driver_col, "completion_rate_pct", "inactive_time_str", "delivered", "to_be", "total"]
        ],
        use_container_width=True
    )


# =========================================================
# 15) 当前映射预览（可选）
# =========================================================
with st.expander("查看当前主表 + 本地补充后的司机映射"):
    mapping_preview = pd.DataFrame({
        "driver_id": list(FINAL_DRIVER_MAP.keys()),
        "team_id": list(FINAL_DRIVER_MAP.values())
    }).sort_values(["team_id", "driver_id"])

    mapping_preview["group"] = mapping_preview["team_id"].map(TEAM_ID_TO_GROUP)
    st.dataframe(mapping_preview, use_container_width=True)
