# -*- coding: utf-8 -*-
"""
生成一份「结构真实、内容模拟」的网页制作岗位原始数据，用于跑通清洗与 EDA 管道。

重要说明
--------
数据是**模拟生成**的，仅用于：
  1. 验证 clean_eda.py 的每一步能跑通、结果可核对；
  2. 给真实数据提供字段 Schema 参考。

拿到真实数据后，把 clean_eda.py 顶部的 RAW_PATH 改掉即可，其余代码不用动。

刻意注入的 7 类脏数据（对应清洗步骤）
------------------------------------
  ① 完全重复行（同公司+岗位+薪资，URL 不同）
  ② 岗位名/描述改写的"伪新岗位"（JD 前 120 字相同）
  ③ 薪资多种写法：面议 / 底薪+提成 / 年薪 / 日薪 / 13薪
  ④ 薪资异常值：80K（架构师混入）、0
  ⑤ 培训机构招生广告（零基础、包就业）
  ⑥ 非目标岗位：网页游戏开发
  ⑦ 文本不规整：城市带"市"后缀、字段含首尾空格、全角括号
"""

import csv
import os
import random

random.seed(20261021)

OUT_DIR = "data/raw"
OUT_PATH = os.path.join(OUT_DIR, "jobs_raw_demo.csv")

FIELDS = [
    "job_title_raw", "company_name", "company_size", "company_type", "industry",
    "city", "district", "salary_raw", "salary_type", "education", "experience",
    "headcount", "skill_tags", "job_desc", "welfare_tags", "publish_date",
    "source_platform", "source_url", "crawl_time",
]

COMPANIES = [
    ("成都云图网络科技有限公司", "20-99人", "建站服务商", "互联网"),
    ("四川创想数字技术有限公司", "100-499人", "建站服务商", "计算机软件"),
    ("成都像素广告传媒有限公司", "20-99人", "广告/代运营", "广告/传媒"),
    ("成都锐意电子商务有限公司", "100-499人", "电商自营", "电子商务"),
    ("四川恒信实业集团有限公司", "500-999人", "企业自有IT", "制造业"),
    ("成都蓝海信息技术有限公司", "20-99人", "建站服务商", "互联网"),
    ("成都微光文化传播有限公司", "20人以下", "广告/代运营", "文化/传媒"),
    ("四川极简软件有限公司", "100-499人", "软件外包", "计算机软件"),
    ("成都星野科技有限责任公司", "20-99人", "电商自营", "电子商务"),
    ("成都优联网络服务有限公司", "100-499人", "建站服务商", "互联网"),
]

DIRECTIONS = {
    "网页制作": {
        "titles": ["网页制作", "网页制作/美工", "网站建设专员", "网页制作工程师"],
        "skills": ["html", "css", "ps", "slice", "template", "cms", "dedecms",
                   "wordpress", "seo", "domain", "server", "buildsite"],
        "salary": (4200, 6800),
    },
    "网页设计": {
        "titles": ["网页设计", "网页美工", "网站设计师", "网页设计师（双休）"],
        "skills": ["ps", "figma", "slice", "banner", "detailpage", "html", "css", "ui"],
        "salary": (4300, 6500),
    },
    "前端开发": {
        "titles": ["Web前端开发", "前端开发工程师", "H5开发工程师", "Web前端"],
        "skills": ["html", "css", "js", "vue", "uniapp", "webpack", "git",
                   "elementui", "typescript"],
        "salary": (7000, 12000),
    },
    "小程序": {
        "titles": ["小程序开发", "小程序开发工程师", "微信小程序开发"],
        "skills": ["miniapp", "uniapp", "js", "html", "css", "vue"],
        "salary": (7200, 10500),
    },
}

KEY_ZH = {
    "html": "HTML", "css": "CSS", "js": "JavaScript", "vue": "Vue", "uniapp": "uni-app",
    "ps": "Photoshop", "slice": "切图", "template": "模板建站", "cms": "CMS建站",
    "dedecms": "织梦", "wordpress": "WordPress", "seo": "SEO", "sem": "SEM",
    "domain": "网站备案", "server": "服务器部署", "figma": "Figma", "banner": "Banner设计",
    "detailpage": "详情页设计", "miniapp": "小程序", "webpack": "Webpack", "git": "Git",
    "elementui": "Element UI", "typescript": "TypeScript", "ui": "UI设计",
    "buildsite": "企业官网建设", "php": "PHP", "mysql": "MySQL",
}

CITIES = [("成都", "武侯区"), ("成都", "高新区"), ("成都", "锦江区"),
          ("成都", "青羊区"), ("成都", "成华区"), ("成都市", "双流区")]
EDUS = ["大专", "专科", "本科", "学历不限", "本科及以上", "大专及以上"]
EXPS = ["应届生", "1年以内", "1-3年", "3-5年", "经验不限"]
WELFARE = ["五险一金|双休", "五险|单休", "五险一金|双休|节日福利", "五险|包住", ""]
PLATFORMS = ["qzw", "zhilian", "58"]


def make_jd(direction, skills, edu, exp):
    """按技能集合拼一段像样的 JD 文本，供词表抽取"""
    words = "、".join(KEY_ZH.get(s, s) for s in skills)
    lines = [
        f"岗位职责：负责{direction}相关工作，能独立完成页面制作与上线；配合业务部门完成需求沟通。",
        f"任职要求：{edu}及以上学历，{exp}相关经验；熟练掌握 {words}。",
    ]
    if "portfolio" in direction:
        lines.append("投递请附作品集。")
    return "\n".join(lines)


def salary_text(lo, hi, kind):
    """生成多种薪资写法，覆盖解析分支。lo/hi 单位为元。"""
    if kind == "plain":
        return f"{lo / 1000:.1f}-{hi / 1000:.1f}K".replace(".0K", "K"), "月薪"
    if kind == "13薪":
        return f"{lo / 1000:.1f}-{hi / 1000:.1f}K·13薪".replace(".0K", "K"), "月薪"
    if kind == "commission":
        return f"{lo}+提成", "底薪+提成"
    if kind == "annual":
        return f"年薪{lo * 12 / 10000:.1f}-{hi * 12 / 10000:.1f}万".replace(".0万", "万"), "年薪"
    if kind == "daily":
        return f"{lo / 21.75:.0f}元/天", "日薪"
    return f"{lo / 1000:.1f}-{hi / 1000:.1f}K", "月薪"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []

    for i in range(40):
        direction = random.choices(list(DIRECTIONS), weights=[35, 22, 33, 10])[0]
        cfg = DIRECTIONS[direction]
        title = random.choice(cfg["titles"])
        company, size, ctype, industry = random.choice(COMPANIES)
        city, district = random.choice(CITIES)
        edu = random.choice(EDUS)
        exp = random.choice(EXPS)

        lo, hi = cfg["salary"]
        edu_adj = {"本科": 800, "本科及以上": 900, "大专": 0, "专科": 0,
                   "学历不限": -300, "大专及以上": 100}[edu]
        exp_adj = {"应届生": -900, "1年以内": -500, "1-3年": 0,
                   "3-5年": 2200, "经验不限": -200}[exp]
        lo = max(3000, lo + edu_adj + exp_adj + random.randint(-300, 400))
        hi = lo + random.randint(1500, 4000)
        # 取整到百位，避免 6221 这种不像真实报价的数字
        lo = int(round(lo / 100) * 100)
        hi = int(round(hi / 100) * 100)

        n_skill = random.randint(4, 7)
        skills = random.sample(cfg["skills"], min(n_skill, len(cfg["skills"])))

        kind = random.choices(["plain", "13薪", "commission", "annual", "daily"],
                              weights=[50, 25, 13, 7, 5])[0]
        if direction == "前端开发" and kind == "commission":
            kind = "13薪"
        if kind == "daily":
            exp = "经验不限"
        s_text, s_type = salary_text(lo, hi, kind)

        rows.append({
            "job_title_raw": title,
            "company_name": company,
            "company_size": size,
            "company_type": ctype,
            "industry": industry,
            "city": city,
            "district": district,
            "salary_raw": s_text,
            "salary_type": s_type,
            "education": edu,
            "experience": exp,
            "headcount": random.choice(["1人", "2人", "3人", "若干"]),
            "skill_tags": "|".join(skills),
            "job_desc": make_jd(direction, skills, edu, exp),
            "welfare_tags": random.choice(WELFARE),
            "publish_date": f"2026-10-{random.randint(1, 20):02d}",
            "source_platform": random.choice(PLATFORMS),
            "source_url": f"https://example.com/job/{10000 + i}",
            "crawl_time": "2026-10-21 16:05:00",
        })

    # ① 完全重复 3 条：只改 URL 和抓取时间
    for i in range(3):
        dup = dict(rows[i])
        dup["source_url"] = f"https://example.com/job/{90000 + i}"
        dup["crawl_time"] = "2026-10-21 17:10:00"
        rows.append(dup)

    # ② 伪新岗位 2 条：岗位名微调、JD 相同
    for i in (5, 6):
        fake = dict(rows[i])
        fake["job_title_raw"] = rows[i]["job_title_raw"] + "（急招）"
        fake["source_url"] = f"https://example.com/job/{91000 + i}"
        rows.append(fake)

    # ③ 培训机构招生广告 3 条
    for i, title in enumerate(["网页设计助理（可零基础）", "网页制作学徒", "UI设计实习生（包就业）"]):
        rows.append({
            "job_title_raw": title,
            "company_name": ["成都某某职业教育学院", "四川某数字艺术学院", "成都某IT实训基地"][i],
            "company_size": "20-99人",
            "company_type": "培训机构",
            "industry": "教育培训",
            "city": "成都",
            "district": "武侯区",
            "salary_raw": random.choice(["面议", "4000-6000K", "3000-5000"]),
            "salary_type": "面议",
            "education": "学历不限",
            "experience": "经验不限",
            "headcount": "若干",
            "skill_tags": "",
            "job_desc": "零基础可培训，包就业，招生中。岗前培训 4 个月，结业推荐就业。",
            "welfare_tags": "",
            "publish_date": "2026-10-18",
            "source_platform": "58",
            "source_url": f"https://example.com/job/{92000 + i}",
            "crawl_time": "2026-10-21 16:05:00",
        })

    # ④ 非目标岗位 2 条
    rows.append({**rows[2], "job_title_raw": "网页游戏开发工程师",
                 "salary_raw": "12-18K", "job_desc": "负责网页游戏客户端开发，熟悉 Egret、Laya 引擎。",
                 "source_url": "https://example.com/job/93001"})
    rows.append({**rows[3], "job_title_raw": "网页游戏运营",
                 "salary_raw": "6-9K", "job_desc": "负责网页游戏活动运营与用户增长。",
                 "source_url": "https://example.com/job/93002"})

    # ⑤ 薪资异常值 2 条（JD 必须给独立文本，否则会先被二级去重规则删掉）
    rows.append({**rows[8], "job_title_raw": "高级前端架构师", "salary_raw": "80-100K",
                 "education": "本科", "experience": "5-10年",
                 "job_desc": "负责前端架构设计与团队管理，制定技术选型规范，要求 8 年以上经验。",
                 "source_url": "https://example.com/job/94001"})
    rows.append({**rows[9], "job_title_raw": "网页制作（急招）", "salary_raw": "0",
                 "job_desc": "负责公司官网日常维护与活动页面制作，长期驻场客户现场。",
                 "source_url": "https://example.com/job/94002"})

    # ⑥ 面议 2 条：验证缺失值处理路径（面议不参与均值，但要单独统计比例）
    for i, (title, desc) in enumerate([
        ("网页制作", "负责企业官网制作与维护，熟练使用 HTML、CSS，会 WordPress 优先。薪资面议。"),
        ("网站建设专员", "负责客户官网搭建、服务器部署与网站备案，熟悉织梦即可。待遇面议。"),
    ]):
        rows.append({**rows[12], "job_title_raw": title, "salary_raw": "面议",
                     "salary_type": "面议", "job_desc": desc, "skill_tags": "",
                     "source_url": f"https://example.com/job/9500{i}"})

    # ⑦ 技能标签缺失 1 条：JD 里其实写了技能，用于验证"用 JD 回填标签"
    rows.append({**rows[14], "job_title_raw": "网页制作/前端",
                 "skill_tags": "",
                 "job_desc": "负责响应式页面制作，熟练 HTML、CSS、JavaScript，会 Vue 更佳，需附作品集。",
                 "source_url": "https://example.com/job/96001"})

    # ⑧ 日薪 1 条：验证 /天 的折算分支（280 × 21.75 ≈ 6090）
    rows.append({**rows[15], "job_title_raw": "网页制作（兼职）", "salary_raw": "280元/天",
                 "salary_type": "日薪", "experience": "经验不限",
                 "job_desc": "兼职制作活动落地页，按单结算，熟练 HTML、CSS 即可。",
                 "source_url": "https://example.com/job/97001"})

    # ⑥ 字段空格 / 全角括号等文本噪声
    rows[10]["company_name"] = "  " + rows[10]["company_name"] + " "
    rows[11]["job_title_raw"] = rows[11]["job_title_raw"].replace("（", "(").replace("）", ")")

    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"已生成 {len(rows)} 条模拟数据 → {OUT_PATH}")
    print("注入问题：3 条完全重复 / 2 条伪新岗位 / 3 条培训广告 / 2 条非目标岗位 / 2 条薪资异常 / 若干文本噪声")


if __name__ == "__main__":
    main()
