import streamlit as st
import pandas as pd
import altair as alt
from datetime import time, datetime

st.set_page_config(page_title="时间段冲突检测", layout="wide")

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
PRIORITIES = ["重要且紧急", "重要不紧急", "紧急不重要", "不重要不紧急"]
P_COLORS = {
    "重要且紧急": "#FF4B4B",  # 红色
    "重要不紧急": "#FFA500",  # 橙色
    "紧急不重要": "#4B9BFF",  # 蓝色
    "不重要不紧急": "#808080"  # 灰色
}

# ---------------- 状态初始化 ----------------
if "slots" not in st.session_state:
    st.session_state.slots = []
if "_next_id" not in st.session_state:
    st.session_state._next_id = 1
if "nonce" not in st.session_state:
    st.session_state.nonce = 0
if "flash" not in st.session_state:
    st.session_state.flash = None
if "checked" not in st.session_state:
    st.session_state.checked = False
if "bulk_errs" not in st.session_state:
    st.session_state.bulk_errs = []

# ---------------- 工具函数 ----------------
def to_min(t: time) -> int:
    return t.hour * 60 + t.minute

def fmt(t: time) -> str:
    return t.strftime("%H:%M")

def min_fmt(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"

def parse_hhmm(s):
    s = str(s).strip().replace("：", ":")
    for f in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(s, f).time()
        except ValueError:
            pass
    return None

def overlap(a, b):
    if a["day"] != b["day"]:
        return None
    s = max(to_min(a["start"]), to_min(b["start"]))
    e = min(to_min(a["end"]), to_min(b["end"]))
    return (s, e) if s < e else None

# 核心算法：按“重要程度”优先贪心
def greedy_keep(slots):
    by_day = {}
    for s in slots:
        by_day.setdefault(s["day"], []).append(s)
    keep = set()
    for _, items in by_day.items():
        # 排序规则：先按重要程度（索引越小越重要），再按结束时间（越早越好）
        ordered = sorted(items, key=lambda x: (PRIORITIES.index(x["priority"]), to_min(x["end"])))
        last_end = -1
        for it in ordered:
            if to_min(it["start"]) >= last_end:
                keep.add(it["id"])
                last_end = to_min(it["end"])
    return keep

def add_slot(name, day, start, end, priority):
    st.session_state.slots.append({
        "id": st.session_state._next_id,
        "name": name, "day": day, "start": start, "end": end, "priority": priority
    })
    st.session_state._next_id += 1

def _parse_bulk(text, up):
    rows, errors = [], []
    if text and text.strip():
        for i, line in enumerate(text.strip().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) not in (4, 5):
                errors.append(f"文本第 {i} 行：需要 4 或 5 列（名称,星期,开始,结束,重要程度）")
                continue
            n, d, s, e = parts[:4]
            p = parts[4] if len(parts) == 5 else "不重要不紧急"
            if p not in PRIORITIES:
                errors.append(f"文本第 {i} 行：重要程度「{p}」无法识别")
                continue
            if d not in WEEKDAYS:
                errors.append(f"文本第 {i} 行：星期「{d}」无法识别")
                continue
            st_, en_ = parse_hhmm(s), parse_hhmm(e)
            if not st_ or not en_:
                errors.append(f"文本第 {i} 行：时间格式应为 HH:MM")
                continue
            if to_min(en_) <= to_min(st_):
                errors.append(f"文本第 {i} 行：结束时间必须晚于开始时间")
                continue
            rows.append((n, d, st_, en_, p))

    if up is not None:
        try:
            try:
                df = pd.read_csv(up, encoding="utf-8-sig")
            except UnicodeDecodeError:
                up.seek(0)
                df = pd.read_csv(up, encoding="gbk")
            cmap = {}
            for c in df.columns:
                lc = str(c).strip().lower()
                if lc in ("名称", "name"): cmap["name"] = c
                elif lc in ("星期", "day", "weekday"): cmap["day"] = c
                elif lc in ("开始", "start", "开始时间"): cmap["start"] = c
                elif lc in ("结束", "end", "结束时间"): cmap["end"] = c
                elif lc in ("重要程度", "priority", "重要"): cmap["priority"] = c
            if not all(k in cmap for k in ("name", "day", "start", "end")):
                errors.append("CSV 缺少必要列（名称/星期/开始/结束）")
            else:
                for idx, row in df.iterrows():
                    rn = idx + 2
                    n = str(row[cmap["name"]]).strip()
                    d = str(row[cmap["day"]]).strip()
                    s = str(row[cmap["start"]]).strip()
                    e = str(row[cmap["end"]]).strip()
                    p = str(row[cmap.get("priority", "")]).strip() if "priority" in cmap else "不重要不紧急"
                    if p not in PRIORITIES: p = "不重要不紧急"
                    if d not in WEEKDAYS:
                        errors.append(f"CSV 第 {rn} 行：星期「{d}」无法识别")
                        continue
                    st_, en_ = parse_hhmm(s), parse_hhmm(e)
                    if not st_ or not en_ or to_min(en_) <= to_min(st_):
                        errors.append(f"CSV 第 {rn} 行：时间格式错误或结束早于开始")
                        continue
                    rows.append((n, d, st_, en_, p))
        except Exception as ex:
            errors.append(f"CSV 读取失败：{ex}")
    return rows, errors

# ---------------- 页面标题 ----------------
st.title("时间段冲突检测")

if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = None

# ---------------- 添加表单 ----------------
with st.form(f"add_form_{st.session_state.nonce}", clear_on_submit=False):
    c1, c2, c3, c4, c5 = st.columns([2.2, 1.2, 1.2, 1.2, 1.8])
    name = c1.text_input("名称", key=f"name_{st.session_state.nonce}", placeholder="例如：高数")
    day = c2.selectbox("星期", WEEKDAYS, key=f"day_{st.session_state.nonce}")
    start = c3.time_input("开始时间", value=time(9, 0), key=f"start_{st.session_state.nonce}")
    end = c4.time_input("结束时间", value=time(10, 0), key=f"end_{st.session_state.nonce}")
    priority = c5.selectbox("重要程度", PRIORITIES, key=f"pri_{st.session_state.nonce}")
    submitted = st.form_submit_button("添加时间段", use_container_width=True)

if submitted:
    name = name.strip()
    if not name:
        st.error("名称不能为空。")
    elif to_min(end) <= to_min(start):
        st.error(f"结束时间（{fmt(end)}）必须晚于开始时间（{fmt(start)}）。")
    else:
        add_slot(name, day, start, end, priority)
        st.session_state.flash = f"已添加：{name}（{day} {fmt(start)}–{fmt(end)}）"
        st.session_state.nonce += 1
        st.rerun()

# ---------------- 批量导入 ----------------
with st.expander("批量导入（粘贴文本 或 上传 CSV）"):
    st.markdown("**方式一：粘贴文本**，每行一条：`名称,星期,HH:MM,HH:MM,重要程度`")
    st.caption("重要程度可填：重要且紧急 / 重要不紧急 / 紧急不重要 / 不重要不紧急（不填默认不重要不紧急）")
    bulk_text = st.text_area("粘贴区", height=110, key="bulk_text", placeholder="高数,周一,09:00,12:00,重要且紧急\n篮球社,周一,10:00,11:00,不重要不紧急", label_visibility="collapsed")
    st.markdown("**方式二：上传 CSV**")
    up = st.file_uploader("CSV 文件", type=["csv"], key="bulk_csv", label_visibility="collapsed")
    if st.button("导入", key="bulk_import"):
        rows, errors = _parse_bulk(bulk_text, up)
        if rows:
            for n, d, s, e, p in rows:
                add_slot(n, d, s, e, p)
            st.session_state.bulk_errs = errors
            msg = f"成功导入 {len(rows)} 条时间段"
            if errors: msg += f"；{len(errors)} 条失败"
            st.session_state.flash = msg
            st.rerun()
        else:
            st.session_state.bulk_errs = errors
            for e in errors: st.error(e)
    if st.session_state.bulk_errs:
        st.markdown("**上次导入的错误：**")
        for e in st.session_state.bulk_errs: st.error(e)

# ---------------- 已添加列表 + 导出 ----------------
slots = st.session_state.slots

if slots:
    st.subheader(f"已添加 {len(slots)} 个时间段")

    # 列表表头
    h1, h2, h3, h4, h5, h6 = st.columns([2.5, 1.2, 1.2, 1.2, 2, 1.2])
    h1.markdown("**名称**")
    h2.markdown("**星期**")
    h3.markdown("**开始**")
    h4.markdown("**结束**")
    h5.markdown("**重要程度**")
    h6.markdown("**操作**")

    # 直接展示表格并每行带删除按钮
    for s in slots:
        c1, c2, c3, c4, c5, c6 = st.columns([2.5, 1.2, 1.2, 1.2, 2, 1.2])
        c1.write(s["name"])
        c2.write(s["day"])
        c3.write(fmt(s["start"]))
        c4.write(fmt(s["end"]))
        # 使用颜色高亮重要程度
        color = P_COLORS.get(s["priority"], "#808080")
        c5.markdown(f'<span style="color:{color}; font-weight:bold;">{s["priority"]}</span>', unsafe_allow_html=True)
        if c6.button("删除", key=f"del_{s['id']}", use_container_width=True):
            st.session_state.slots = [x for x in st.session_state.slots if x["id"] != s["id"]]
            st.session_state.checked = False
            st.rerun()

    st.divider()

    # 操作按钮区
    df_show = pd.DataFrame([
        {"名称": s["name"], "星期": s["day"], "开始": fmt(s["start"]), "结束": fmt(s["end"]), "重要程度": s["priority"]}
        for s in slots
    ])
    csv_bytes = df_show.to_csv(index=False).encode("utf-8-sig")
    
    c_export, c_check, c_clear = st.columns([2, 2, 1])
    c_export.download_button("导出表格", data=csv_bytes, file_name="时间段.csv", mime="text/csv", use_container_width=True)
    
    if c_check.button("检查冲突", type="primary", use_container_width=True):
        st.session_state.checked = True
        
    if c_clear.button("清空全部", use_container_width=True):
        st.session_state.slots = []
        st.session_state.checked = False
        st.session_state.bulk_errs = []
        st.rerun()

    # ---------------- 冲突检测与时间轴 ----------------
    if st.session_state.checked:
        conflicts = []
        for i in range(len(slots)):
            for j in range(i + 1, len(slots)):
                ov = overlap(slots[i], slots[j])
                if ov:
                    conflicts.append((slots[i], slots[j], ov))

        if not conflicts:
            st.success("没有检测到任何冲突，所有时间段都可以保留。")
        else:
            st.error(f"检测到 {len(conflicts)} 处冲突：")
            for a, b, (s, e) in conflicts:
                st.error(f"「{a['name']}」和「{b['name']}」在{a['day']} {min_fmt(s)}–{min_fmt(e)} 冲突")

            # 时间轴图表（可以根据重要程度显示颜色，或者根据冲突显示红色）
            base = pd.Timestamp("2000-01-01")
            recs = []
            for s in slots:
                recs.append({
                    "名称": s["name"],
                    "星期": s["day"],
                    "开始": base + pd.to_timedelta(to_min(s["start"]), unit="m"),
                    "结束": base + pd.to_timedelta(to_min(s["end"]), unit="m"),
                    "重要程度": s["priority"],
                    "时间": f"{s['day']} {fmt(s['start'])}–{fmt(s['end'])}",
                })
            df_tl = pd.DataFrame(recs)

            st.markdown("**时间轴**")
            chart_key = f"timeline_chart_{hash(tuple(sorted([str(s['id']) + s['name'] for s in slots])))}"
            
            # 让时间轴的颜色跟随“重要程度”变化
            chart = (
                alt.Chart(df_tl)
                .mark_bar(size=16, cornerRadius=4)
                .encode(
                    x=alt.X("开始:T", title="时间", axis=alt.Axis(format="%H:%M")),
                    x2="结束:T",
                    y=alt.Y("星期:N", sort=WEEKDAYS, title=None),
                    yOffset=alt.YOffset("名称:N"),
                    color=alt.Color(
                        "重要程度:N", 
                        scale=alt.Scale(
                            domain=PRIORITIES, 
                            range=[P_COLORS[p] for p in PRIORITIES]
                        ),
                        legend=alt.Legend(title="重要程度")
                    ),
                    tooltip=["名称", "星期", "时间", "重要程度"],
                )
                .properties(height=280)
            )
            st.altair_chart(chart, use_container_width=True, key=chart_key)

            # 重新计算保留建议
            keep_ids = greedy_keep(slots)
            removed = [s for s in slots if s["id"] not in keep_ids]
            kept = [s for s in slots if s["id"] in keep_ids]

            if removed:
                # 按重要程度和开始时间排序，让优先级的展示更明显
                kept.sort(key=lambda x: (PRIORITIES.index(x["priority"]), to_min(x["start"])))
                removed.sort(key=lambda x: (PRIORITIES.index(x["priority"]), to_min(x["start"])))
                
                st.success("优先参加以下行程：\n\n" + "\n".join(f"- **{s['name']}**（{s['day']} {fmt(s['start'])}–{fmt(s['end'])}，{s['priority']}）" for s in kept))
                st.warning("建议放弃以下行程：\n\n" + "\n".join(f"- {s['name']}（{s['day']} {fmt(s['start'])}–{fmt(s['end'])}，{s['priority']}）" for s in removed))
else:
    st.info("还没有任何时间段，请在上方添加。")
