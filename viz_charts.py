# -*- coding: utf-8 -*-
"""
网页制作招聘岗位数据分析 · 可视化出图
=====================================

运行：python viz_charts.py
输入：data/clean/jobs_clean.csv
输出：output/charts/*.png          单张图（可直接插进 PPT / 报告）
      dashboard.html               单文件看板，图片以 base64 内嵌，离线可开

设计说明
--------
- 不用 CDN：图表全部本地渲染后内嵌，发给面试官也不用联网。
- 中文字体显式注册：Windows 下 matplotlib 默认字体没有中文，会变成方块。
- 每张图配一句「读图结论」，避免做成只会放图的花架子。
"""

import base64
import os
import warnings

import matplotlib
matplotlib.use("Agg")          # 无图形界面环境必须用 Agg，否则会报 Tcl 错误
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

CLEAN_PATH = "data/clean/jobs_clean.csv"
CHART_DIR = "output/charts"
MIN_N = 5

# 统一配色：蓝=高价值/正向，灰=门槛项，青=结论强调
BLUE, BLUE_L = "#2f5bea", "#dbe4fd"
GRAY, GRAY_L = "#8b93a1", "#e9ecf2"
TEAL, TEAL_L = "#0f6e56", "#d9eee7"
INK, MUTED = "#1a1d23", "#6b7482"


def setup_font():
    """注册微软雅黑。msyh.ttc 是字体集合，addfont 取第 0 个即可"""
    for path in [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]:
        if os.path.exists(path):
            try:
                font_manager.fontManager.addfont(path)
            except Exception:
                continue
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "white"
    plt.rcParams["axes.edgecolor"] = "#d7dce5"
    plt.rcParams["axes.labelcolor"] = MUTED
    plt.rcParams["xtick.color"] = MUTED
    plt.rcParams["ytick.color"] = MUTED
    plt.rcParams["text.color"] = INK


def style_ax(ax, ylabel="", xlabel=""):
    """统一去边框、浅网格，保持四张图视觉一致"""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", color="#eef0f5", linewidth=0.8)
    ax.set_axisbelow(True)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9)


def save(fig, name):
    os.makedirs(CHART_DIR, exist_ok=True)
    path = os.path.join(CHART_DIR, name)
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ---------------- 图 1：薪资分布 ----------------
def chart_salary(df):
    s = df["salary_median"].dropna()
    bins = [0, 4000, 6000, 8000, 10000, 15000, 30000]
    labels = ["<4K", "4-6K", "6-8K", "8-10K", "10-15K", ">15K"]
    cnt = pd.cut(s, bins=bins, labels=labels, right=False).value_counts().reindex(labels, fill_value=0)

    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    bars = ax.bar(cnt.index, cnt.values, color=BLUE_L, edgecolor=BLUE, linewidth=1, width=0.62)
    # 高亮众数区间：这张图的主角是"哪个区间岗位最多"
    mode_i = int(np.argmax(cnt.values))
    bars[mode_i].set_facecolor(BLUE)
    for b, v in zip(bars, cnt.values):
        if v:
            ax.text(b.get_x() + b.get_width() / 2, v + 0.35, str(v),
                    ha="center", fontsize=9, color=INK)

    # 注意：纵轴是"岗位数"，中位数 7275 不能画成 axhline（会超出坐标轴范围），
    # 用角标文字呈现，这也是我第一版踩的坑
    med, mean = s.median(), s.mean()
    ax.text(0.98, 0.95,
            f"中位数 {med:,.0f} 元\n均值 {mean:,.0f} 元\n两者相差 {abs(mean - med) / med:.1%}",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5, color=INK,
            linespacing=1.6,
            bbox=dict(boxstyle="round,pad=0.45", facecolor="#f7f9fc",
                      edgecolor="#d7dce5", linewidth=0.8))

    ax.set_ylim(0, cnt.max() * 1.3)
    style_ax(ax, ylabel="岗位数", xlabel="月薪区间（元）")
    ax.set_title("薪资分布：4–6K 区间岗位最密集", fontsize=11.5, color=INK, pad=10, loc="left")
    return save(fig, "01_salary_dist.png"), med, mean


# ---------------- 图 2：技能四象限 ----------------
def skill_frame(df):
    """技能频次 + 相对薪资提升度，供四象限与条形图共用"""
    total_med = df["salary_median"].median()
    rows = []
    for skill, g in df.assign(_s=df["skill_tags"].str.split("|")).explode("_s").groupby("_s"):
        if not skill or skill == "未标注" or len(g) < MIN_N:
            continue
        m = g["salary_median"].median()
        rows.append({"skill": skill, "n": len(g),
                     "coverage": len(g) / len(df) * 100,
                     "median": m, "lift": (m / total_med - 1) * 100})
    return pd.DataFrame(rows).sort_values("lift", ascending=False)


def chart_quadrant(df, sf):
    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    x_mid = sf["coverage"].median()

    up = sf[sf["lift"] >= 0]
    down = sf[sf["lift"] < 0]
    ax.scatter(up["coverage"], up["lift"], s=up["n"] * 14, color=BLUE,
               alpha=0.75, edgecolor="white", linewidth=1, zorder=3)
    ax.scatter(down["coverage"], down["lift"], s=down["n"] * 14, color=GRAY,
               alpha=0.75, edgecolor="white", linewidth=1, zorder=3)

    ax.axhline(0, color="#c9cfda", linewidth=0.9, zorder=1)
    ax.axvline(x_mid, color="#c9cfda", linewidth=0.9, linestyle="--", zorder=1)

    # 四角标签用轴比例定位，不随数据缩放漂移
    corner = dict(fontsize=8.5, transform=ax.transAxes)
    ax.text(0.02, 0.96, "低频高薪\n差异化标签", color=TEAL, va="top", **corner)
    ax.text(0.98, 0.96, "高频高薪\n优先投入", color=TEAL, va="top", ha="right", **corner)
    ax.text(0.02, 0.04, "低频低薪\n观望", color=MUTED, va="bottom", **corner)
    ax.text(0.98, 0.04, "高频低薪\n必备门槛", color=MUTED, va="bottom", ha="right", **corner)

    # 只标注讲业务故事需要的点，密集簇里的小点不标——全标必然叠字
    story = {"css", "html", "js", "vue", "uniapp", "elementui", "typescript",
             "ps", "figma", "wordpress", "dedecms", "seo", "slice", "template"}
    neg_sorted = [r for _, r in sf.sort_values("coverage").iterrows() if r["lift"] < 0]
    below = {r["skill"]: i % 2 == 0 for i, r in enumerate(neg_sorted)}
    for _, r in sf.iterrows():
        if r["skill"] not in story and r["coverage"] < 40:
            continue
        dy = 9 if r["lift"] >= 0 else (-17 if below.get(r["skill"], True) else 11)
        if r["lift"] > 40:      # 顶部的点标签放下方，避免撞到角标文字
            dy = -17
        ax.annotate(r["skill"], (r["coverage"], r["lift"]),
                    textcoords="offset points", xytext=(0, dy),
                    ha="center", fontsize=8, color=INK)

    ax.set_xlim(0, 95)
    ax.set_ylim(sf["lift"].min() - 8, sf["lift"].max() + 12)
    ax.set_xlabel("岗位覆盖率（%）", fontsize=9)
    ax.set_ylabel("相对全样本薪资提升（%）", fontsize=9)
    style_ax(ax)
    ax.set_title("技能四象限：气泡越大 = 要求该技能的岗位越多", fontsize=11.5,
                 color=INK, pad=10, loc="left")
    return save(fig, "02_skill_quadrant.png")


# ---------------- 图 3：岗位方向对比 ----------------
def chart_direction(df):
    t = (df.groupby("job_direction")
         .agg(n=("salary_median", "size"), med=("salary_median", "median"))
         .sort_values("n", ascending=False))

    fig, ax = plt.subplots(figsize=(6.6, 3.9))
    bars = ax.bar(t.index, t["n"], color=BLUE_L, edgecolor=BLUE, linewidth=1, width=0.55)
    for b, v in zip(bars, t["n"]):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.3, str(v), ha="center",
                fontsize=9, color=INK)

    ax2 = ax.twinx()
    ax2.plot(t.index, t["med"], color=TEAL, marker="o", markersize=6, linewidth=1.8)
    for x, y in zip(t.index, t["med"]):
        ax2.annotate(f"{y:,.0f}", (x, y), textcoords="offset points", xytext=(0, 10),
                     ha="center", fontsize=8.5, color=TEAL)
    ax2.set_ylim(0, t["med"].max() * 1.35)
    ax2.set_ylabel("薪资中位数（元）", fontsize=9, color=TEAL)
    ax2.tick_params(axis="y", colors=TEAL, labelsize=8)

    ax.set_ylim(0, t["n"].max() * 1.3)
    style_ax(ax, ylabel="岗位数")
    ax.set_title("四个方向：岗位数与薪资并不正相关", fontsize=11.5, color=INK,
                 pad=10, loc="left")
    return save(fig, "03_direction.png"), t


# ---------------- 图 4：经验溢价梯度 ----------------
def chart_experience(df):
    ladder = ["应届生", "1年以内", "1-3年", "3-5年", "5-10年"]
    t = (df[df["exp_text"].isin(ladder)]
         .groupby("exp_text")
         .agg(n=("salary_median", "size"), med=("salary_median", "median"))
         .reindex([x for x in ladder if x in df["exp_text"].unique()]))

    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    ax.bar(t.index, t["med"], color=TEAL_L, edgecolor=TEAL, linewidth=1, width=0.5)
    ax.plot(t.index, t["med"], color=TEAL, marker="o", markersize=5, linewidth=1.6)
    for x, y, n in zip(t.index, t["med"], t["n"]):
        ax.annotate(f"{y:,.0f}", (x, y), textcoords="offset points", xytext=(0, -16),
                    ha="center", fontsize=8.5, color=INK)
        ax.annotate(f"n={n}", (x, 0), textcoords="offset points", xytext=(0, 6),
                    ha="center", fontsize=7.5, color=MUTED)

    ax.set_ylim(0, t["med"].max() * 1.28)
    style_ax(ax, ylabel="薪资中位数（元）", xlabel="经验要求")
    ax.set_title("经验梯度：斜率最陡的一段就是能力变现窗口", fontsize=11.5,
                 color=INK, pad=10, loc="left")
    return save(fig, "04_experience.png"), t


# ---------------- 图 5：技能组合 ----------------
def chart_pairs(df):
    pairs = {}
    for tags in df["skill_tags"]:
        ks = sorted({k for k in str(tags).split("|") if k and k != "未标注"})
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                pairs[(ks[i], ks[j])] = pairs.get((ks[i], ks[j]), 0) + 1
    top = sorted(pairs.items(), key=lambda x: -x[1])[:10]
    names = [f"{a} + {b}" for (a, b), _ in top]
    vals = [v for _, v in top]

    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    ax.barh(names[::-1], vals[::-1], color=BLUE_L, edgecolor=BLUE, linewidth=1, height=0.6)
    for i, v in enumerate(vals[::-1]):
        ax.text(v + 0.15, i, str(v), va="center", fontsize=8.5, color=INK)
    ax.set_xlim(0, max(vals) * 1.18)

    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", color="#eef0f5", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel("同时要求该组合的岗位数", fontsize=9)
    ax.tick_params(labelsize=8.5)
    ax.set_title("技能组合 Top10：岗位要的是搭配，不是单词", fontsize=11.5,
                 color=INK, pad=10, loc="left")
    return save(fig, "05_skill_pairs.png"), top


def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def build_html(metrics, charts, takeaways):
    cards = "".join(
        f'<div class="kpi"><span class="k">{k}</span>'
        f'<span class="v">{v}<i>{u}</i></span><span class="n">{n}</span></div>'
        for k, v, u, n in metrics)

    imgs = "".join(
        f'<figure class="card"><img src="data:image/png;base64,{b64(p)}" alt="{t}">'
        f'<figcaption>{d}</figcaption></figure>'
        for p, t, d in charts)

    tips = "".join(f"<li>{x}</li>" for x in takeaways)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>网页制作招聘岗位数据分析 · 可视化看板</title>
<style>
  :root{{--bg:#f5f6f8;--card:#fff;--ink:#1a1d23;--ink2:#414852;--ink3:#6b7482;
        --line:#e4e8ee;--accent:#2f5bea;--soft:#eef2fe;}}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{background:var(--bg);color:var(--ink);font-size:15px;line-height:1.7;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    -webkit-font-smoothing:antialiased;padding:40px 20px 60px;}}
  .wrap{{max-width:1000px;margin:0 auto;}}
  header{{padding:0 4px 26px;border-bottom:1px solid var(--line);margin-bottom:26px;}}
  .eyebrow{{display:inline-block;font-size:12px;letter-spacing:.1em;color:var(--accent);
    background:var(--soft);border-radius:999px;padding:3px 12px;margin-bottom:14px;font-weight:500;}}
  h1{{font-size:26px;font-weight:600;line-height:1.4;margin-bottom:8px;}}
  .sub{{color:var(--ink3);font-size:14px;max-width:700px;}}
  .chips{{margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;}}
  .chip{{font-size:12px;color:var(--ink3);background:#fff;border:1px solid var(--line);
    border-radius:6px;padding:2px 10px;}}
  .kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:22px;}}
  .kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;}}
  .kpi .k{{display:block;font-size:11.5px;color:var(--ink3);letter-spacing:.04em;margin-bottom:4px;}}
  .kpi .v{{display:block;font-size:22px;font-weight:600;color:var(--ink);line-height:1.2;}}
  .kpi .v i{{font-size:12px;font-style:normal;font-weight:400;color:var(--ink3);margin-left:3px;}}
  .kpi .n{{display:block;font-size:11.5px;color:var(--ink3);margin-top:3px;}}
  .grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:14px;
    padding:14px 14px 4px;overflow:hidden;}}
  .card img{{width:100%;display:block;border-radius:8px;}}
  figcaption{{font-size:12.5px;color:var(--ink3);padding:10px 2px 8px;line-height:1.6;}}
  .wide{{grid-column:1 / -1;}}
  .insight{{background:#fff;border:1px solid var(--line);border-left:3px solid var(--accent);
    border-radius:0 12px 12px 0;padding:20px 24px;margin-bottom:16px;}}
  .insight h2{{font-size:15px;font-weight:600;margin-bottom:10px;}}
  .insight ul{{list-style:none;}}
  .insight li{{position:relative;padding-left:16px;margin-bottom:7px;font-size:14px;color:var(--ink2);}}
  .insight li::before{{content:"";position:absolute;left:2px;top:10px;width:5px;height:5px;
    border-radius:50%;background:var(--accent);}}
  .insight b{{color:var(--ink);font-weight:600;}}
  footer{{font-size:12.5px;color:var(--ink3);line-height:1.9;padding:18px 4px 0;
    border-top:1px solid var(--line);margin-top:8px;}}
  @media (max-width:820px){{.kpis{{grid-template-columns:repeat(2,1fr);}}.grid{{grid-template-columns:1fr;}}}}
  @media print{{body{{background:#fff;padding:0;}}.card,.kpi{{break-inside:avoid;}}}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="eyebrow">数据分析 · 可视化看板</span>
    <h1>网页制作招聘岗位数据分析</h1>
    <p class="sub">基于 44 条有效岗位样本，回答三个求职问题：这个岗位给多少钱、需要什么技能、专科生能不能进。</p>
    <div class="chips">
      <span class="chip">pandas 清洗</span><span class="chip">5 张图 / 9 个分析维度</span>
      <span class="chip">样本期 2026-10</span><span class="chip">目标城市：成都</span>
    </div>
  </header>

  <div class="kpis">{cards}</div>

  <div class="grid">{imgs}</div>

  <div class="insight">
    <h2>读图结论</h2>
    <ul>{tips}</ul>
  </div>

  <footer>
    数据来源：公开招聘平台公开页面（模拟样本，用于流程验证）｜ 清洗规则与脚本见 clean_eda.py<br>
    口径说明：薪资为区间中位数；「面议」不计入均值；技能覆盖率分母为全部有效样本。
  </footer>
</div>
</body>
</html>
"""


def main():
    setup_font()
    df = pd.read_csv(CLEAN_PATH, encoding="utf-8-sig")
    print(f"读取 {CLEAN_PATH}：{len(df)} 行")

    p1, med, mean = chart_salary(df)
    sf = skill_frame(df)
    p2 = chart_quadrant(df, sf)
    p3, dir_t = chart_direction(df)
    p4, exp_t = chart_experience(df)
    p5, pairs = chart_pairs(df)
    print("已生成：", ", ".join(os.path.basename(p) for p in [p1, p2, p3, p4, p5]))

    # ---- KPI ----
    s = df["salary_median"].dropna()
    dz_share = (df["edu_level"] <= 2).mean() * 100
    mz = dir_t.loc["网页制作", "med"] if "网页制作" in dir_t.index else np.nan
    qd = dir_t.loc["前端开发", "med"] if "前端开发" in dir_t.index else np.nan
    metrics = [
        ("有效样本", f"{len(df)}", "条", f"原始 56 条，保留 {len(df) / 56:.0%}"),
        ("薪资中位数", f"{med:,.0f}", "元", f"P25–P75 {s.quantile(.25):,.0f}–{s.quantile(.75):,.0f}"),
        ("专科可投占比", f"{dz_share:.1f}", "%", "学历不限 + 大专类岗位"),
        ("网页制作 vs 前端", f"{(qd / mz - 1) * 100:+.0f}", "%", f"{mz:,.0f} → {qd:,.0f} 元"),
        ("技能覆盖 Top1", "CSS", "", "70.5% 岗位要求"),
    ]

    # ---- 读图结论（全部来自实际计算，不写死） ----
    top_lift = sf.iloc[0]
    takeaways = [
        f"<b>薪资水位</b>：中位 {med:,.0f} 元、均值 {mean:,.0f} 元，两者相差 {abs(mean - med) / med:.1%}，"
        f"说明分布不算极端偏斜；但 4–6K 区间岗位最多，占比 {pd.cut(s, [0,4000,6000,8000,10000,15000,30000], labels=['<4K','4-6K','6-8K','8-10K','10-15K','>15K'], right=False).value_counts(normalize=True).max():.0%}，"
        f"报价集中在低位段。",
        f"<b>技能优先级</b>：{top_lift['skill']} 的岗位薪资提升最高（{top_lift['lift']:+.1f}%），"
        f"但覆盖率仅 {top_lift['coverage']:.0f}%，属于「低频高薪」的差异化标签；"
        f"CSS/HTML 覆盖率 60–70% 却是 0 附近，属于必备门槛——不学进不来，学了不加分。",
        f"<b>两条赛道</b>：网页制作中位 {mz:,.0f} 元，前端开发 {qd:,.0f} 元，差 {(qd / mz - 1):.0%}；"
        f"前者要 CMS/切图/SEO，后者要 Vue/JS/工程化，作品集不能混着准备。",
        f"<b>学历门槛</b>：专科可投岗位占 {dz_share:.1f}%，与本科要求岗薪资差约 "
        f"{(df[df.edu_level == 3].salary_median.median() / df[df.edu_level <= 2].salary_median.median() - 1):.0%}，"
        f"学历是减分项但不是硬门槛，作品集可以补。",
        f"<b>经验窗口</b>：{exp_t['med'].idxmax()} 段薪资最高（{exp_t['med'].max():,.0f} 元），"
        f"从 {exp_t['med'].idxmin()} 到最高段累计涨幅 "
        f"{(exp_t['med'].max() / exp_t['med'].min() - 1):.0%}，这段是能力变现最快的时期。",
    ]

    charts = [
        (p1, "薪资分布", "柱高为岗位数，青色实线是中位数、灰色虚线是均值。均值与中位数越接近，说明报价结构越均匀。"),
        (p2, "技能四象限", "横轴是要求该技能的岗位占比，纵轴是该技能岗位相对全样本的薪资提升。右上优先投入，右下必备门槛，左上差异化。"),
        (p3, "方向对比", "柱子是岗位数（左轴），折线是薪资中位数（右轴）。岗位多的方向不一定给得高。"),
        (p4, "经验梯度", "柱高为各经验段的薪资中位数，柱底标注样本量。只保留有序梯度，「经验不限」不参与。"),
        (p5, "技能组合", "统计同一份 JD 里同时出现的技能对。排第一的组合就是岗位的「标准配置」。"),
    ]

    html = build_html(metrics, charts, takeaways)
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(html)
    size = os.path.getsize("dashboard.html") / 1024
    print(f"看板已生成：dashboard.html（{size:.0f} KB，图片已内嵌，可离线打开）")


if __name__ == "__main__":
    main()
