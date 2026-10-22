# -*- coding: utf-8 -*-
"""
网页制作招聘岗位数据分析 · 数据清洗与 EDA
=========================================

运行：python clean_eda.py
输入：data/raw/jobs_raw_demo.csv（换真实数据只改 RAW_PATH）
输出：data/clean/jobs_clean.csv     清洗后宽表，后续分析与画图都用它
      data/clean/jobs_rejected.csv  被剔除记录 + 原因，可追溯
      data/clean/cleaning_log.csv   每步行数变化，写报告时可引用
      output/eda_*.csv              各分析维度的结果表

设计原则
--------
1. 每一步都记录"清洗前后行数"，最后能回答"我的样本怎么了"。
2. 被剔除的行不丢弃，另存并写明原因——作品集里能体现数据治理意识。
3. 清洗与 EDA 严格分开：清洗只做可验证的规则，EDA 才做业务解读。
"""

import csv
import os
import re

import numpy as np
import pandas as pd

# 需要复用上一轮做的技能词表；没有就跳过技能回填，不影响主流程
try:
    from skill_dict import load_matchers, to_row
    MATCHERS = load_matchers("skill_dict.csv")
except Exception as e:  # noqa: BLE001
    MATCHERS = None
    print(f"[警告] 技能词表未加载，跳过技能回填：{e}")

RAW_PATH = "data/raw/jobs_raw_demo.csv"
CLEAN_PATH = "data/clean/jobs_clean.csv"
REJECT_PATH = "data/clean/jobs_rejected.csv"
LOG_PATH = "data/clean/cleaning_log.csv"
OUT_DIR = "output"

# 薪资合理区间：低于 1K 视为录入错误，高于 60K 视为非目标岗位（架构/管理）
SALARY_MIN, SALARY_MAX = 1000, 60000
MIN_N = 5  # 分组统计的最小样本量，低于它不下结论

pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 130)
pd.set_option("display.max_columns", 60)


# ============================================================
# 一、清洗工具函数
# ============================================================

def norm_text(s):
    """文本标准化：去首尾与多余空格、全角括号转半角、连续空白压成一个"""
    if pd.isna(s):
        return ""
    s = str(s).replace("（", "(").replace("）", ")").replace("　", " ")
    return re.sub(r"\s+", " ", s).strip()


def norm_city(s):
    """城市名去掉行政后缀，避免"成都"与"成都市"被当成两个城市"""
    s = norm_text(s)
    return re.sub(r"(市|地区)$", "", s)


UNIT = {"k": 1000, "千": 1000, "w": 10000, "万": 10000}
NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([kK千万wW]?)")


def parse_salary(raw):
    """
    把各种薪资写法统一成「月薪下限 / 上限 / 月数」。

    覆盖的真实写法：
        15-25K / 6.5-8.2K·13薪 / 7000+提成 / 年薪12-18万 / 250元/天 / 面议 / 6千-1.2万
    返回 dict，解析失败不抛异常——一条脏数据不该中断整批。
    """
    out = {"salary_low": np.nan, "salary_high": np.nan,
           "salary_months": 12, "salary_form": "未知", "salary_parsed": 0}

    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        out["salary_form"] = "缺失"
        return out

    s = str(raw).strip().replace(" ", "").replace("～", "-").replace("－", "-").replace("至", "-")
    if not s:
        out["salary_form"] = "缺失"
        return out
    if "面议" in s:
        out["salary_form"] = "面议"
        return out

    # 先摘掉「13薪」这类月数后缀，否则 13 会被当成薪资数字
    m = re.search(r"(\d{1,2})\s*薪", s)
    if m:
        months = int(m.group(1))
        if 12 <= months <= 24:
            out["salary_months"] = months
        s = s[: m.start()].rstrip("·-*x×")

    is_daily = ("元/天" in s) or ("/天" in s)
    is_annual = ("年薪" in s) or ("/年" in s)

    nums = [(float(n), u.lower()) for n, u in NUM_RE.findall(s)]
    if not nums:
        out["salary_form"] = "无法解析"
        return out

    if len(nums) == 1:
        lo = hi = nums[0][0] * UNIT.get(nums[0][1], 1)
    else:
        (lo, u1), (hi, u2) = nums[0], nums[1]
        # "15-25K" 这种前半段不带单位的，沿用后半段的单位
        u1 = u1 or u2
        u2 = u2 or u1
        lo, hi = lo * UNIT.get(u1, 1), hi * UNIT.get(u2, 1)

    if lo > hi:  # 偶发的上下限写反
        lo, hi = hi, lo

    if is_daily:
        lo, hi = lo * 21.75, hi * 21.75     # 按每月 21.75 个工作日折算
        out["salary_form"] = "日薪"
    elif is_annual:
        lo, hi = lo / 12, hi / 12
        out["salary_form"] = "年薪"
    elif "提成" in s:
        out["salary_form"] = "底薪+提成"
    else:
        out["salary_form"] = "月薪"

    out.update(salary_low=round(lo), salary_high=round(hi),
               salary_parsed=1)
    return out


EDU_MAP = {"学历不限": 0, "不限": 0, "高中": 1, "中专": 1, "大专": 2, "专科": 2,
           "大专及以上": 2, "本科": 3, "本科及以上": 3, "硕士": 4, "硕士及以上": 4}

EXP_MAP = {"应届生": 0, "应届": 0, "无经验": 0, "经验不限": 0, "1年以内": 0.5,
           "1-3年": 1, "3-5年": 3, "5-10年": 5, "10年以上": 10}


def norm_edu(s):
    s = norm_text(s)
    return EDU_MAP.get(s, np.nan)


def norm_exp(s):
    s = norm_text(s)
    return EXP_MAP.get(s, np.nan)


def job_direction(title):
    """岗位名归并成四个方向。这是主观口径，写报告时要在局限性里说明"""
    t = norm_text(title)
    if "小程序" in t:
        return "小程序"
    if any(k in t for k in ["前端", "H5", "h5"]):
        return "前端开发"
    if any(k in t for k in ["制作", "建站", "网站建设", "官网"]):
        return "网页制作"
    if any(k in t for k in ["设计", "美工"]):
        return "网页设计"
    return "其他"


# ============================================================
# 二、清洗主流程
# ============================================================

log_rows = []


def log_step(step, before, after, note=""):
    log_rows.append({"清洗步骤": step, "清洗前": before, "清洗后": after,
                     "剔除": before - after,
                     "保留率": f"{after / before:.1%}" if before else "-",
                     "说明": note})
    print(f"  [{step}] {before} → {after} 行（剔除 {before - after}）")


def main():
    print("=" * 78)
    print("一、读取原始数据")
    print("=" * 78)
    # dtype=str 很关键：先全部按文本读，避免 pandas 把 "0"、"1-3年" 猜成奇怪类型
    raw = pd.read_csv(RAW_PATH, encoding="utf-8-sig", dtype=str).fillna("")
    print(f"原始数据：{raw.shape[0]} 行 × {raw.shape[1]} 列")
    print(f"列名：{list(raw.columns)}")
    n0 = len(raw)
    df = raw.copy()
    rejected = []

    # ---------- 步骤 1：文本标准化 ----------
    print("\n" + "=" * 78)
    print("二、数据清洗")
    print("=" * 78)
    before = len(df)
    for col in ["job_title_raw", "company_name", "city", "district", "education",
                "experience", "salary_raw", "company_type", "industry"]:
        if col in df.columns:
            df[col] = df[col].map(norm_text)
    df["city"] = df["city"].map(norm_city)
    log_step("1.文本标准化", before, len(df), "去空格/全角括号、城市去行政后缀")

    # ---------- 步骤 2：剔除无关岗位 ----------
    # 业务含义：招聘平台上大量"零基础可培训"是招生广告，不是真岗位；
    # "网页游戏"是游戏行业，与网页制作无关。不剔除会污染薪资中位数。
    before = len(df)
    title_and_desc = (df["job_title_raw"] + " " + df["job_desc"]).str.lower()

    train_keywords = ["零基础", "包就业", "招生", "学徒", "岗前培训", "实训", "培训"]
    game_keywords = ["网页游戏", "游戏开发", "游戏运营", "laya", "egret"]

    is_train = title_and_desc.apply(lambda t: any(k in t for k in train_keywords))
    is_game = df["job_title_raw"].str.contains("|".join(game_keywords), na=False, case=False)

    rejected.append(df[is_train].assign(reject_reason="疑似培训机构/招生广告"))
    rejected.append(df[is_game].assign(reject_reason="非目标岗位：网页游戏"))
    df = df[~(is_train | is_game)].copy()
    log_step("2.剔除无关岗位", before, len(df), f"培训广告 {is_train.sum()} 条、游戏岗 {is_game.sum()} 条")

    # ---------- 步骤 3：去重 ----------
    # 业务含义：HR 反复刷新发布，同一岗位会有多个 URL。只按 URL 去重会漏掉大量重复。
    # 一级：公司+岗位+薪资+城市 完全一致 → 判定为同一岗位
    # 二级：同公司且 JD 前 120 字一致 → 识别"改个标题重发"
    before = len(df)
    df["_fp_exact"] = (df["company_name"] + "|" + df["job_title_raw"] + "|"
                       + df["salary_raw"] + "|" + df["city"])
    dup_exact = df.duplicated(subset="_fp_exact", keep="first")

    df["_fp_desc"] = (df["company_name"] + "|"
                      + df["job_desc"].str.replace(r"\s+", "", regex=True).str[:120])
    dup_desc = df.duplicated(subset="_fp_desc", keep="first") & (~dup_exact)

    rejected.append(df[dup_exact].assign(reject_reason="重复：公司+岗位+薪资+城市完全一致"))
    rejected.append(df[dup_desc].assign(reject_reason="重复：同公司 JD 前120字相同"))
    df = df[~(dup_exact | dup_desc)].copy()
    log_step("3.去重", before, len(df), f"完全重复 {dup_exact.sum()} 条、伪新岗位 {dup_desc.sum()} 条")

    # ---------- 步骤 4：薪资解析与异常值 ----------
    before = len(df)
    sal = df["salary_raw"].apply(parse_salary).apply(pd.Series)
    df = pd.concat([df, sal], axis=1)

    # 解析失败率是数据质量的核心指标，要单独看
    fail_rate = 1 - df["salary_parsed"].mean()
    print(f"  薪资解析成功率：{df['salary_parsed'].mean():.1%}"
          f"（面议 {(df['salary_form'] == '面议').sum()} 条）")

    # 硬边界：明显不是目标岗位的薪资
    hard_out = ((df["salary_low"] < SALARY_MIN) | (df["salary_high"] > SALARY_MAX))
    rejected.append(df[hard_out].assign(reject_reason="薪资异常值（低于1K或高于60K）"))
    df = df[~hard_out].copy()

    # IQR 只用于报告，不用于删除：样本小的时候 IQR 会把真实的高薪前端岗误判成异常
    df["salary_median"] = (df["salary_low"] + df["salary_high"]) / 2
    valid = df["salary_median"]
    q1, q3 = valid.quantile([0.25, 0.75])
    iqr_lo, iqr_hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    n_iqr = ((valid < iqr_lo) | (valid > iqr_hi)).sum()
    print(f"  IQR 参考区间 [{iqr_lo:.0f}, {iqr_hi:.0f}]，疑似离群 {n_iqr} 条（仅标记，不删除）")
    log_step("4.薪资解析与异常值", before, len(df),
             f"解析成功 {df['salary_parsed'].mean():.1%}，剔除硬边界 {hard_out.sum()} 条")

    # ---------- 步骤 5：学历与经验标准化 ----------
    # 业务含义：原始是文本（"大专"/"专科"/"本科及以上"），无法排序和计算。
    # 映射成有序数值后才能算"学历溢价"。
    before = len(df)
    df["edu_level"] = df["education"].map(norm_edu)
    df["exp_min"] = df["experience"].map(norm_exp)
    df["edu_unmapped"] = df["edu_level"].isna()
    df["exp_unmapped"] = df["exp_min"].isna()
    log_step("5.学历经验映射", before, len(df),
             f"学历未匹配 {df['edu_unmapped'].sum()} 条、经验未匹配 {df['exp_unmapped'].sum()} 条")

    # ---------- 步骤 6：缺失值处理 ----------
    # 业务含义：缺失本身是信息。"面议"多说明小公司报价不透明；学历"未标注"多是小公司。
    # 所以用"未标注"占位而不是删行——删行会把小公司整体从样本里抹掉，产生选择偏差。
    before = len(df)
    miss_before = df[["edu_level", "exp_min", "company_type", "industry"]].isna().sum()
    df["edu_level"] = df["edu_level"].fillna(2).astype(int)   # 未标注按大专处理（保守）
    df["edu_text"] = df["education"].where(df["education"] != "", "未标注")
    df["exp_min"] = df["exp_min"].fillna(0)
    df["exp_text"] = df["experience"].where(df["experience"] != "", "未标注")
    for col in ["company_type", "industry", "welfare_tags", "skill_tags"]:
        df[col] = df[col].replace("", "未标注")

    # 技能标签缺失时，用 JD 文本回填（词表抽取），避免技能分析丢样本
    if MATCHERS is not None:
        need_fill = (df["skill_tags"] == "未标注")
        filled = 0
        for idx in df[need_fill].index:
            extracted = to_row(df.at[idx, "job_desc"], MATCHERS)["skill_tags"]
            if extracted:
                df.at[idx, "skill_tags"] = extracted
                filled += 1
        print(f"  技能标签回填：{filled} 条（从 JD 文本抽取）")
    log_step("6.缺失值处理", before, len(df), "缺失用\"未标注\"占位，技能用 JD 回填，不删行")

    # ---------- 步骤 7：类型转换 ----------
    before = len(df)
    df["publish_date"] = pd.to_datetime(df["publish_date"], errors="coerce")
    df["headcount_num"] = (df["headcount"].str.extract(r"(\d+)")[0]
                           .pipe(pd.to_numeric, errors="coerce"))
    df["salary_low"] = pd.to_numeric(df["salary_low"], errors="coerce")
    df["salary_high"] = pd.to_numeric(df["salary_high"], errors="coerce")
    df["salary_median"] = pd.to_numeric(df["salary_median"], errors="coerce")
    df["job_direction"] = df["job_title_raw"].map(job_direction)
    df["skill_count"] = df["skill_tags"].apply(
        lambda s: 0 if s == "未标注" else len([x for x in s.split("|") if x]))
    df = df.drop(columns=["_fp_exact", "_fp_desc"])

    df = df[["job_direction", "job_title_raw", "company_name", "company_size",
             "company_type", "industry", "city", "district", "salary_raw",
             "salary_form", "salary_low", "salary_high", "salary_months",
             "salary_median", "education", "edu_text", "edu_level", "experience",
             "exp_text", "exp_min", "headcount_num", "skill_tags", "skill_count",
             "job_desc", "welfare_tags", "publish_date", "source_platform",
             "source_url", "crawl_time"]]
    log_step("7.类型转换", before, len(df), "日期/薪资/人数转数值，生成岗位方向与技能数")

    # ---------- 保存 ----------
    os.makedirs("data/clean", exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(CLEAN_PATH, index=False, encoding="utf-8-sig")
    rej = pd.concat(rejected, ignore_index=True) if rejected else pd.DataFrame()
    if not rej.empty:
        rej.to_csv(REJECT_PATH, index=False, encoding="utf-8-sig")
    pd.DataFrame(log_rows).to_csv(LOG_PATH, index=False, encoding="utf-8-sig")

    print(f"\n清洗日志：")
    print(pd.DataFrame(log_rows).to_string(index=False))
    print(f"\n干净数据 {len(df)} 行 → {CLEAN_PATH}")
    print(f"剔除记录 {len(rej)} 行 → {REJECT_PATH}"
          f"（保留率 {len(df) / n0:.1%}，原始 {n0} 行）")

    # ========================================================
    # 三、EDA
    # ========================================================
    eda_overview(df)
    eda_salary(df)
    eda_experience(df)
    eda_education(df)
    eda_skills(df)
    eda_cooccurrence(df)
    eda_direction(df)
    eda_company(df)
    eda_region(df)


def save_table(t, name):
    t.to_csv(os.path.join(OUT_DIR, name), encoding="utf-8-sig")
    return t


def title(s):
    print("\n" + "=" * 78)
    print(s)
    print("=" * 78)


# ============================================================
# 三、EDA 各维度
# ============================================================

def eda_overview(df):
    """维度 0：样本概览 —— 先判断这份数据能不能用来下结论"""
    title("EDA-0 样本概览（判断样本可信度）")
    print(f"有效样本：{len(df)} 条    时间范围：{df['publish_date'].min().date()} ~ "
          f"{df['publish_date'].max().date()}")
    print(f"薪资缺失（面议）：{(df['salary_form'] == '面议').sum()} 条 "
          f"({(df['salary_form'] == '面议').mean():.1%})")

    t1 = df["job_direction"].value_counts().rename_axis("岗位方向").reset_index(name="岗位数")
    t1["占比"] = (t1["岗位数"] / len(df)).map("{:.1%}".format)
    print("\n[岗位方向分布]")
    print(t1.to_string(index=False))
    save_table(t1, "eda_00_岗位方向分布.csv")

    t2 = (df.groupby(["city", "district"]).size().rename("岗位数")
          .reset_index().sort_values("岗位数", ascending=False))
    print("\n[城市 / 区域分布]")
    print(t2.to_string(index=False))
    save_table(t2, "eda_01_区域分布.csv")

    t3 = df["source_platform"].value_counts().rename_axis("平台").reset_index(name="岗位数")
    print("\n[来源平台分布]")
    print(t3.to_string(index=False))
    save_table(t3, "eda_02_平台分布.csv")
    print("\n业务含义：方向/区域/平台任何一项过度集中，结论就只能代表那个子市场；"
          "\n面议比例高说明报价不透明，均值不可信，应改用中位数。")


def eda_salary(df):
    """维度 1：薪资分布 —— 市场水位，以及均值陷阱"""
    title("EDA-1 薪资分布（市场水位）")
    s = df["salary_median"].dropna()
    q = s.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).round(0)
    print(q.to_string())

    mean, median = s.mean(), s.median()
    diff = mean - median
    sk = s.skew()
    shape = ("右偏（长尾在高薪端）" if sk > 0.2
             else "左偏（长尾在低薪端）" if sk < -0.2 else "近似对称")
    print(f"\n均值 {mean:,.0f} 元  vs  中位数 {median:,.0f} 元  "
          f"→ 相差 {diff:+,.0f} 元（{diff / median:+.1%}）")
    print(f"偏度 {sk:.2f} —— {shape}")
    print(f"均值与中位数相差 {abs(diff) / median:.1%}，"
          f"{'两种口径接近，结论一致' if abs(diff) / median < 0.05 else '差距偏大，应以中位数汇报'}")

    bins = [0, 4000, 6000, 8000, 10000, 15000, 30000]
    labels = ["<4K", "4-6K", "6-8K", "8-10K", "10-15K", ">15K"]
    t = (pd.cut(s, bins=bins, labels=labels, right=False).value_counts()
         .sort_index().rename_axis("薪资区间").reset_index(name="岗位数"))
    t["占比"] = (t["岗位数"] / len(s)).map("{:.1%}".format)
    print("\n[薪资区间分布]")
    print(t.to_string(index=False))
    save_table(t, "eda_03_薪资区间分布.csv")

    top = t.loc[t["岗位数"].idxmax()]
    print("\n业务含义：中位数才是「典型岗位」的报价，均值会被两端拉偏。")
    print(f"→ 可写进简历的结论：{top['薪资区间']} 区间岗位最多"
          f"（{top['岗位数']} 条 / {top['占比']}），中位月薪 {median:,.0f} 元，"
          f"P25–P75 区间 {s.quantile(.25):,.0f}–{s.quantile(.75):,.0f} 元。")


LADDER = ["应届生", "1年以内", "1-3年", "3-5年", "5-10年"]


def eda_experience(df):
    """维度 2：经验 × 薪资 —— 经验溢价曲线，判断「几年一跳」最划算"""
    title("EDA-2 经验要求与薪资（经验溢价）")
    t = (df.groupby("exp_text")
         .agg(岗位数=("salary_median", "size"),
              薪资中位数=("salary_median", "median"),
              薪资均值=("salary_median", "mean"))
         .round(0).reset_index())

    # 只有「有序梯度」之间才能算涨幅。"经验不限 / 未标注"不是某一段经验，
    # 混进梯度里算 pct_change 会得出毫无意义的涨幅。
    ladder = t[t["exp_text"].isin(LADDER)].copy()
    ladder["_o"] = ladder["exp_text"].map({k: i for i, k in enumerate(LADDER)})
    ladder = ladder.sort_values("_o").drop(columns="_o")
    ladder["相邻涨幅"] = (ladder["薪资中位数"].pct_change()
                          .map(lambda x: f"{x:+.1%}" if pd.notna(x) else "-"))
    ladder["样本提示"] = ladder["岗位数"].map(lambda n: "" if n >= MIN_N else "样本少")
    print("[有序经验梯度]")
    print(ladder.to_string(index=False))

    other = t[~t["exp_text"].isin(LADDER)]
    if len(other):
        print("\n[非梯度：经验不限 / 未标注]（不参与涨幅计算）")
        print(other.to_string(index=False))
    save_table(pd.concat([ladder, other]), "eda_04_经验薪资.csv")

    def med(exp):
        v = t.loc[t["exp_text"] == exp, "薪资中位数"]
        return float(v.iloc[0]) if len(v) else None

    a, b = med("1-3年"), med("3-5年")
    if a and b:
        print(f"\n1-3年 → 3-5年：{b - a:+,.0f} 元（{b / a - 1:+.1%}）")
    print("\n业务含义：梯度上的斜率就是经验溢价。斜率最陡的那一段，"
          "\n是能力最容易被市场重新定价的窗口，应优先在这一阶段补齐高价值技能。")


EDU_LABEL = {0: "学历不限", 1: "高中/中专", 2: "大专", 3: "本科", 4: "硕士"}


def eda_education(df):
    """维度 3：学历门槛与溢价 —— 专科生的真实可投空间"""
    title("EDA-3 学历要求与薪资（专科生可投空间）")
    # 原始写法有「大专 / 专科 / 大专及以上」三种，必须先映射成有序等级再分组，口径才一致
    t = (df.assign(学历=df["edu_level"].map(EDU_LABEL))
         .groupby("学历")
         .agg(岗位数=("salary_median", "size"),
              薪资中位数=("salary_median", "median"),
              薪资上限中位=("salary_high", "median"))
         .round(0).reset_index().sort_values("岗位数", ascending=False))
    t["占比"] = (t["岗位数"] / len(df)).map("{:.1%}".format)
    t["样本提示"] = t["岗位数"].map(lambda n: "" if n >= MIN_N else "样本少")
    print(t.to_string(index=False))
    save_table(t, "eda_05_学历薪资.csv")

    dz = df[df["edu_level"] <= 2]
    bk = df[df["edu_level"] == 3]
    share = len(dz) / len(df)
    print(f"\n专科可投（学历不限 / 大专类）岗位占比：{share:.1%}")

    if len(dz) >= MIN_N and len(bk) >= MIN_N:
        dz_m, bk_m = dz["salary_median"].median(), bk["salary_median"].median()
        gap, gap_pct = bk_m - dz_m, bk_m / dz_m - 1
        print(f"专科可投岗位中位薪资 {dz_m:,.0f} 元，本科要求岗位 {bk_m:,.0f} 元，"
              f"差距 {gap:+,.0f} 元（{gap_pct:+.1%}）")
        if share >= 0.5 and gap_pct <= 0.20:
            print("→ 结论：可投面广、学历溢价低，说明是「技能导向」岗位，对专科生是机会窗口。")
        else:
            print("→ 结论：学历溢价明显或可投面偏窄，简历第一屏应优先用作品集与项目对冲。")
    else:
        print("→ 样本量不足，不下学历溢价结论。")

    print("\n业务含义：这条决定简历第一屏写什么——学历溢价低就主打作品与技能，"
          "\n溢价高就主打可验证的项目成果与量化指标。")


def skill_names():
    """从词表取 技能key → 中文名。图表和简历里用中文名，可读性更好"""
    mapping = {}
    try:
        with open("skill_dict.csv", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                mapping.setdefault(row["skill_key"], row["skill_name"])
    except Exception:
        pass
    return mapping


def eda_skills(df):
    """维度 4：技能频次与薪资提升度 —— 学习优先级清单"""
    title("EDA-4 技能需求（学什么）")
    s = df["skill_tags"].str.split("|").explode()
    s = s[(s.str.len() > 0) & (s != "未标注")]   # 未标注不是技能，不能进频次
    names = skill_names()
    freq = (s.value_counts().rename_axis("技能").reset_index(name="出现次数"))
    freq["技能名称"] = freq["技能"].map(names).fillna(freq["技能"])
    freq["岗位覆盖率"] = (freq["出现次数"] / len(df)).map("{:.1%}".format)
    freq = freq[["技能", "技能名称", "出现次数", "岗位覆盖率"]]
    print("[技能频次 Top 15]")
    print(freq.head(15).to_string(index=False))
    save_table(freq, "eda_06_技能频次.csv")

    # 技能 - 薪资提升度：命中该技能的岗位，中位薪资相对全样本高多少
    total_median = df["salary_median"].median()
    rows = []
    for skill, group in df.assign(_s=df["skill_tags"].str.split("|")).explode("_s").groupby("_s"):
        if not skill or skill == "未标注" or len(group) < MIN_N:
            continue
        m = group["salary_median"].median()
        rows.append({"技能": skill, "岗位数": len(group), "薪资中位数": m,
                     "相对全样本": f"{(m / total_median - 1):+.1%}"})
    lift = pd.DataFrame(rows).sort_values("薪资中位数", ascending=False) if rows else pd.DataFrame()
    if not lift.empty:
        lift.insert(1, "技能名称", lift["技能"].map(names).fillna(lift["技能"]))
        print(f"\n[技能—薪资提升度]（仅统计样本 ≥{MIN_N} 的技能，全样本中位 {total_median:,.0f} 元）")
        print(lift.to_string(index=False))
        save_table(lift, "eda_07_技能薪资提升度.csv")

    print("\n业务含义：高频 + 低薪 = 必备门槛（不学进不来）；高频 + 高薪 = 优先投入；"
          "\n低频 + 高薪 = 差异化标签（简历亮点）。这张表就是你的学习路线图。")
    print("注意：提升度没有控制岗位方向——PS 的低提升度本质是「设计岗薪资低」，"
          "\n不是「学 PS 会降薪」。要拆开方向效应，需在方向内做分层比较。")


def eda_cooccurrence(df):
    """维度 5：技能共现 —— 岗位真实要的是"组合"，不是单个技能"""
    title("EDA-5 技能组合（技能共现）")
    pairs = {}
    for tags in df["skill_tags"]:
        ks = sorted({k for k in str(tags).split("|") if k and k != "未标注"})
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                pairs[(ks[i], ks[j])] = pairs.get((ks[i], ks[j]), 0) + 1
    t = (pd.DataFrame([{"技能A": a, "技能B": b, "同时要求岗位数": c}
                       for (a, b), c in pairs.items()])
         .sort_values("同时要求岗位数", ascending=False).head(12))
    print(t.to_string(index=False))
    save_table(t, "eda_08_技能组合.csv")
    print("\n业务含义：共现最高的组合就是岗位的「标准配置」。"
          "\n面试被问\"你会什么\"时，按组合答比罗列单词更有说服力。")


def eda_direction(df):
    """维度 6：岗位方向对比 —— 项目的核心差异化结论"""
    title("EDA-6 岗位方向对比（网页制作 vs 前端）")
    t = (df.groupby("job_direction")
         .agg(岗位数=("salary_median", "size"),
              薪资中位数=("salary_median", "median"),
              薪资下限中位=("salary_low", "median"),
              薪资上限中位=("salary_high", "median"),
              平均技能数=("skill_count", "mean"))
         .round(1).reset_index().sort_values("岗位数", ascending=False))
    print(t.to_string(index=False))
    save_table(t, "eda_09_方向对比.csv")

    print("\n[各方向的高频技能 Top5]")
    for d, g in df.groupby("job_direction"):
        s = g["skill_tags"].str.split("|").explode()
        top = s[s.str.len() > 0].value_counts().head(5)
        print(f"  {d}({len(g)}条)：{'、'.join(f'{k}({v})' for k, v in top.items())}")

    print("\n业务含义：如果「网页制作/建站」集中在 HTML/CSS/PS/CMS/SEO，"
          "\n而「前端开发」集中在 Vue/JS/工程化，说明这是两个不同赛道。"
          "\n求职时按赛道准备作品，比笼统说「我会做网页」精准得多。")

    def dmed(name):
        v = t.loc[t["job_direction"] == name, "薪资中位数"]
        return float(v.iloc[0]) if len(v) else None

    mz, qd = dmed("网页制作"), dmed("前端开发")
    if mz and qd:
        print(f"→ 网页制作 {mz:,.0f} 元 vs 前端开发 {qd:,.0f} 元："
              f"差 {qd - mz:+,.0f} 元（{qd / mz - 1:+.1%}）")


def eda_company(df):
    """维度 7：企业类型与规模 —— 去哪类公司投"""
    title("EDA-7 企业类型 / 规模与薪资")
    for col in ["company_type", "company_size"]:
        t = (df.groupby(col)
             .agg(岗位数=("salary_median", "size"),
                  薪资中位数=("salary_median", "median"))
             .round(0).reset_index().sort_values("岗位数", ascending=False))
        t["样本提示"] = t["岗位数"].map(lambda n: "" if n >= MIN_N else "样本少，只看量不看薪")
        print(f"\n[按{col}]")
        print(t.to_string(index=False))
        save_table(t, f"eda_10_{col}.csv")
    print("\n业务含义：岗位数量最多的企业类型，不一定是薪资最高的。"
          "\n这条决定了投递策略是「广撒网拿面试」还是「精准投高薪」——"
          "\n两者的简历侧重点完全不同。")


def eda_region(df):
    """维度 8：区域分布 —— 投递区域与通勤成本"""
    title("EDA-8 区域分布")
    t = (df.groupby("district")
         .agg(岗位数=("salary_median", "size"),
              薪资中位数=("salary_median", "median"),
              最高薪资=("salary_high", "max"))
         .round(0).reset_index().sort_values("岗位数", ascending=False))
    print(t.to_string(index=False))
    save_table(t, "eda_11_区域薪资.csv")
    print("\n业务含义：岗位密度和薪资往往反向——中心城区岗位多但租金高。"
          "\n严格做法应结合区域租金算\"薪资/房租\"比值，这里先给出密度与水位，"
          "\n租金数据作为下一步补充（也是报告的局限性之一）。")


if __name__ == "__main__":
    main()
