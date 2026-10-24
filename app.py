import streamlit as st
from datetime import time

st.set_page_config(page_title="时间段冲突检测", page_icon="⏰", layout="centered")

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# ---------------- 状态初始化 ----------------
if "slots" not in st.session_state:
    st.session_state.slots = []          # [{"id", "name", "day", "start", "end"}]
if "_next_id" not in st.session_state:
    st.session_state._next_id = 1

# ---------------- 工具函数 ----------------
def to_min(t: time) -> int:
    """把 time 转成当天的分钟数，方便比较。"""
    return t.hour * 60 + t.minute

def fmt(t: time) -> str:
    return t.strftime("%H:%M")

def min_fmt(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"

def overlap(a, b):
    """两个时间段若冲突，返回重叠区间的 (起始分钟, 结束分钟)，否则返回 None。"""
    if a["day"] != b["day"]:
        return None
    s = max(to_min(a["start"]), to_min(b["start"]))
    e = min(to_min(a["end"]), to_min(b["end"]))
    return (s, e) if s < e else None

def greedy_keep(slots):
    """按结束时间贪心，返回“最多能保留”的时间段的 id 集合（最大无冲突子集）。"""
    by_day = {}
    for s in slots:
        by_day.setdefault(s["day"], []).append(s)

    keep_ids = set()
    for _, items in by_day.items():
        # 关键：按结束时间从早到晚排序（结束相同则开始早的优先）
        ordered = sorted(items, key=lambda x: (to_min(x["end"]), to_min(x["start"])))
        last_end = -1
        for it in ordered:
            if to_min(it["start"]) >= last_end:   # 与已保留的都不重叠，就保留
                keep_ids.add(it["id"])
                last_end = to_min(it["end"])
    return keep_ids

# ---------------- 页面标题 ----------------
st.title("⏰ 时间段冲突检测小工具")
st.caption("添加时间段 → 检查冲突 → 拿到「最少删几个」的建议")

# ---------------- 添加时间段 ----------------
with st.form("add_form", clear_on_submit=False):
    c1, c2, c3, c4 = st.columns([2.2, 1.2, 1.2, 1.2])
    name = c1.text_input("名称", placeholder="例如：高数")
    day = c2.selectbox("星期", WEEKDAYS, index=0)
    start = c3.time_input("开始时间", value=time(9, 0))
    end = c4.time_input("结束时间", value=time(10, 0))
    submitted = st.form_submit_button("➕ 添加时间段", use_container_width=True)

if submitted:
    name = name.strip()
    if not name:
        st.error("名称不能为空，请输入一个名称（例如：高数、篮球社）。")
    elif to_min(end) <= to_min(start):
        st.error(
            f"结束时间（{fmt(end)}）必须晚于开始时间（{fmt(start)}），请重新填写。"
        )
    else:
        st.session_state.slots.append(
            {
                "id": st.session_state._next_id,
                "name": name,
                "day": day,
                "start": start,
                "end": end,
            }
        )
        st.session_state._next_id += 1
        st.success(f"已添加：{name}（{day} {fmt(start)}–{fmt(end)}）")

# ---------------- 已添加列表 ----------------
slots = st.session_state.slots

if slots:
    st.subheader(f"📋 已添加 {len(slots)} 个时间段")
    for i, s in enumerate(slots):
        col1, col2, col3 = st.columns([3, 3, 1])
        col1.markdown(f"**{s['name']}**")
        col2.markdown(f"{s['day']} {fmt(s['start'])} – {fmt(s['end'])}")
        if col3.button("删除", key=f"del_{s['id']}", use_container_width=True):
            st.session_state.slots.pop(i)
            st.rerun()

    st.divider()
    btn_col1, btn_col2 = st.columns([3, 1])
    do_check = btn_col1.button("🔍 检查冲突", type="primary", use_container_width=True)
    if btn_col2.button("清空全部", use_container_width=True):
        st.session_state.slots = []
        st.rerun()

    # ---------------- 冲突检测 ----------------
    if do_check:
        conflicts = []
        n = len(slots)
        for i in range(n):
            for j in range(i + 1, n):
                ov = overlap(slots[i], slots[j])
                if ov:
                    conflicts.append((slots[i], slots[j], ov))

        if not conflicts:
            st.success("🎉 没有检测到任何冲突，所有时间段都可以保留。")
        else:
            st.error(f"检测到 {len(conflicts)} 处冲突：")
            for a, b, (s, e) in conflicts:
                st.error(
                    f"「{a['name']}」和「{b['name']}」在{a['day']} "
                    f"{min_fmt(s)}–{min_fmt(e)} 冲突"
                )

            # ---- 贪心建议 ----
            keep_ids = greedy_keep(slots)
            removed = [s for s in slots if s["id"] not in keep_ids]
            kept = [s for s in slots if s["id"] in keep_ids]

            st.warning(
                f"按结束时间贪心：最多可同时保留 {len(kept)} 个时间段，"
                f"最少需要删掉 {len(removed)} 个。"
            )
            if removed:
                st.warning("建议删除以下时间段：\n\n"
                           + "\n".join(
                               f"- **{s['name']}**（{s['day']} {fmt(s['start'])}–{fmt(s['end'])}）"
                               for s in removed
                           ))
                st.info("删除后保留（互不冲突）：\n\n"
                        + "\n".join(
                            f"- {s['name']}（{s['day']} {fmt(s['start'])}–{fmt(s['end'])}）"
                            for s in kept
                        ))
else:
    st.info("还没有任何时间段，先在上方添加吧。")