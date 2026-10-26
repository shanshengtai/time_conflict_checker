import streamlit as st
import pandas as pd
import altair as alt
from datetime import time, datetime

st.set_page_config(page_title="时间段冲突检测", page_icon="⏰", layout="wide")

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# ---------------- 状态初始化 ----------------
if "slots" not in st.session_state:
    st.session_state.slots = []
if "_next_id" not in st.session_state:
    st.session_state._next_id = 1
if "nonce" not in st.session_state:
    st.session_state.nonce = 0          # 用于添加成功后重置表单控件
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
    """把 'HH:MM' / 'HH:MM:SS' 解析成 time，失败返回 None。"""
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

def greedy_keep(slots):
    """按结束时间贪心，返回最多能保留的时间段的 id 集合。"""
    by_day = {}
    for s in slots:
        by_day.setdefault(s["day"], []).append(s)
    keep = set()
    for _, items in by_day.items():
        ordered = sorted(items, key=lambda x: (to_min(x["end"]), to_min(x["start"])))
        last_end = -1
        for it in ordered:
            if to_min(it["start"]) >= last_end:
                keep.add(it["id"])
                last_end = to_min(it["end"])
    return keep

def add_slot(name, day, start, end):
    st.session_state.slots.append({
        "id": st.session_state._next_id,
        "name": name, "day": day, "start": start, "end": end,
    })
    st.session_state._next_id += 1

def _parse_bulk(text, up):
    """解析粘贴文本 + 上传 CSV，返回 (rows, errors)。"""
    rows, errors = [], []

    if text and text.strip():
        for i, line in enumerate(text.strip().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) != 4:
                errors.append(f"文本第 {i} 行：需要 4 列（名称,星期,HH:MM,HH:MM）")
                continue
            n, d, s, e = parts
            if d not in WEEKDAYS:
                errors.append(f"文本第 {i} 行：星期「{d}」无法识别（应为 周一…周日）")
                continue
            st_, en_ = parse_hhmm(s), parse_hhmm(e)
            if not st_ or not en_:
                errors.append(f"文本第 {i} 行：时间格式应为 HH:MM")
                continue
            if to_min(en_) <= to_min(st_):
                errors.append(f"文本第 {i} 行：结束时间必须晚于开始时间")
                continue
            rows.append((n, d, st_, en_))

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
                if lc in ("名称", "name"):
                    cmap["name"] = c
                elif lc in ("星期", "day", "weekday"):
                    cmap["day"] = c
                elif lc in ("开始", "start", "开始时间"):
                    cmap["start"] = c
                elif lc in ("结束", "end", "结束时间"):
                    cmap["end"] = c
            if not all(k in cmap for k in ("name", "day", "start", "end")):
                errors.append("CSV 缺少必要列（名称/星期/开始/结束）")
            else:
                for idx, row in df.iterrows():
                    rn = idx + 2
                    n = str(row[cmap["name"]]).strip()
                    d = str(row[cmap["day"]]).strip()
                    s = str(row[cmap["start"]]).strip()
                    e = str(row[cmap["end"]]).strip()
                    if d not in WEEKDAYS:
                        errors.append(f"CSV 第 {rn} 行：星期「{d}」无法识别")
                        continue
                    st_, en_ = parse_hhmm(s), parse_hhmm(e)
                    if not st_ or not en_:
                        errors.append(f"CSV 第 {rn} 行：时间格式应为 HH:MM")
                        continue
                    if to_min(en_) <= to_min(st_):
                        errors.append(f"CSV 第 {rn} 行：结束时间必须晚于开始时间")
                        continue
                    rows.append((n, d, st_, en_))
        except Exception as ex:
            errors.append(f"CSV 读取失败：{ex}")

    return rows, errors

# ---------------- 页面标题 ----------------
st.title("⏰ 时间段冲突检测小工具")

if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = None

# ---------------- 添加表单 ----------------
with st.form(f"add_form_{st.session_state.nonce}", clear_on_submit=False):
    c1, c2, c3, c4 = st.columns([2.2, 1.2, 1.2, 1.2])
    name = c1.text_input("名称", key=f"name_{st.session_state.nonce}", placeholder="例如：高数")
    day = c2.selectbox("星期", WEEKDAYS, key=f"day_{st.session_state.nonce}")
    start = c3.time_input("开始时间", value=time(9, 0), key=f"start_{st.session_state.nonce}")
    end = c4.time_input("结束时间", value=time(10, 0), key=f"end_{st.session_state.nonce}")
    submitted = st.form_submit_button("➕ 添加时间段", use_container_width=True)

if submitted:
    name = name.strip()
    if not name:
        st.error("名称不能为空，请输入一个名称（例如：高数、篮球社）。")
    elif to_min(end) <= to_min(start):
        st.error(f"结束时间（{fmt(end)}）必须晚于开始时间（{fmt(start)}），请重新填写。")
    else:
        add_slot(name, day, start, end)
        st.session_state.flash = f"已添加：{name}（{day} {fmt(start)}–{fmt(end)}）"
        st.session_state.nonce += 1   # 换一组新 key，相当于清空输入框
        st.rerun()

# ---------------- 批量导入 ----------------
with st.expander("📥 批量导入（粘贴文本 或 上传 CSV）"):
    st.markdown("**方式一：粘贴文本**，每行一条：`名称,星期,HH:MM,HH:MM`")
    bulk_text = st.text_area(
        "粘贴区", height=110, key="bulk_text",
        placeholder="高数,周一,09:00,10:00\n篮球社,周三,14:00,16:00",
        label_visibility="collapsed",
    )
    st.markdown("**方式二：上传 CSV**，列：名称 / 星期 / 开始 / 结束")
    up = st.file_uploader("CSV 文件", type=["csv"], key="bulk_csv", label_visibility="collapsed")
    if st.button("导入", key="bulk_import"):
        rows, errors = _parse_bulk(bulk_text, up)
        if rows:
            for n, d, s, e in rows:
                add_slot(n, d, s, e)
            st.session_state.bulk_errs = errors
            msg = f"成功导入 {len(rows)} 条时间段"
            if errors:
                msg += f"；{len(errors)} 条失败，详见导入区错误提示"
            st.session_state.flash = msg
            st.rerun()
        else:
            st.session_state.bulk_errs = errors
            for e in errors:
                st.error(e)

    if st.session_state.bulk_errs:
        st.markdown("**上次导入的错误：**")
        for e in st.session_state.bulk_errs:
            st.error(e)

# ---------------- 已添加列表 + 导出 ----------------
slots = st.session_state.slots

if slots:
    st.subheader(f"📋 已添加 {len(slots)} 个时间段")

    df_show = pd.DataFrame([
        {"名称": s["name"], "星期": s["day"], "开始": fmt(s["start"]), "结束": fmt(s["end"])}
        for s in slots
    ])
    st.dataframe(df_show, use_container_width=True, hide_index=True)

    csv_bytes = df_show.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ 导出 CSV",
        data=csv_bytes,
        file_name="时间段.csv",
        mime="text/csv",
    )

    label_to_id = {}
    for i, s in enumerate(slots, 1):
        label_to_id[f"{i}. {s['name']}（{s['day']} {fmt(s['start'])}–{fmt(s['end'])}）"] = s["id"]
    sel = st.multiselect("选择要删除的时间段", list(label_to_id.keys()))
    dcol1, dcol2 = st.columns([3, 1])
    if dcol2.button("删除所选", use_container_width=True, disabled=not sel):
        ids = {label_to_id[x] for x in sel}
        st.session_state.slots = [s for s in st.session_state.slots if s["id"] not in ids]
        st.session_state.flash = f"已删除 {len(ids)} 个时间段"
        st.session_state.checked = False
        st.rerun()

    st.divider()
    btn_col1, btn_col2 = st.columns([3, 1])
    if btn_col1.button("🔍 检查冲突", type="primary", use_container_width=True):
        st.session_state.checked = True
    if btn_col2.button("清空全部", use_container_width=True):
        st.session_state.slots = []
        st.session_state.checked = False
        st.session_state.bulk_errs = []
        st.rerun()

    # ---------------- 冲突检测 ----------------
    if st.session_state.checked:
        conflicts = []
        for i in range(len(slots)):
            for j in range(i + 1, len(slots)):
                ov = overlap(slots[i], slots[j])
                if ov:
                    conflicts.append((slots[i], slots[j], ov))

        if not conflicts:
            st.success("🎉 没有检测到任何冲突，所有时间段都可以保留。")
        else:
            st.error(f"检测到 {len(conflicts)} 处冲突：")
            for a, b, (s, e) in conflicts:
                st.error(f"「{a['name']}」和「{b['name']}」在{a['day']} {min_fmt(s)}–{min_fmt(e)} 冲突")

            # ---- 时间轴 ----
            conflict_ids = set()
            for a, b, _ in conflicts:
                conflict_ids.add(a["id"])
                conflict_ids.add(b["id"])

            base = pd.Timestamp("2000-01-01")
            recs = []
            for s in slots:
                recs.append({
                    "名称": s["name"],
                    "星期": s["day"],
                    "开始": base + pd.to_timedelta(to_min(s["start"]), unit="m"),
                    "结束": base + pd.to_timedelta(to_min(s["end"]), unit="m"),
                    "状态": "冲突" if s["id"] in conflict_ids else "正常",
                    "时间": f"{s['day']} {fmt(s['start'])}–{fmt(s['end'])}",
                })
            df_tl = pd.DataFrame(recs)

            st.markdown("**🕒 时间轴（红色为冲突段）**")
            chart = (
                alt.Chart(df_tl)
                .mark_bar(size=16, cornerRadius=4)
                .encode(
                    x=alt.X("开始:T", title="时间", axis=alt.Axis(format="%H:%M")),
                    x2="结束:T",
                    y=alt.Y("星期:N", sort=WEEKDAYS, title=None),
                    yOffset=alt.YOffset("名称:N"),
                    color=alt.Color(
                        "状态:N",
                        scale=alt.Scale(domain=["正常", "冲突"], range=["#4C78A8", "#E45756"]),
                        legend=alt.Legend(title=None),
                    ),
                    tooltip=["名称", "星期", "时间", "状态"],
                )
                .properties(height=280)
            )
            st.altair_chart(chart, use_container_width=True)

            # ---- 贪心建议 ----
            keep_ids = greedy_keep(slots)
            removed = [s for s in slots if s["id"] not in keep_ids]
            kept = [s for s in slots if s["id"] in keep_ids]

            st.warning(
                f"按结束时间贪心：最多可同时保留 {len(kept)} 个时间段，"
                f"最少需要删掉 {len(removed)} 个。"
            )
            if removed:
                st.warning("建议删除：\n\n" + "\n".join(
                    f"- **{s['name']}**（{s['day']} {fmt(s['start'])}–{fmt(s['end'])}）"
                    for s in removed
                ))
                st.info("删除后保留（互不冲突）：\n\n" + "\n".join(
                    f"- {s['name']}（{s['day']} {fmt(s['start'])}–{fmt(s['end'])}）"
                    for s in kept
                ))
else:
    st.info("还没有任何时间段，先在上方添加或批量导入吧。")
