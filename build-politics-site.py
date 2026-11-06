#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 /politics/ 板块：各年试卷页、data/*.js、首页 index.html，并复制原卷 / 解析 PDF。

用法：python3 build-politics-site.py [年份...]
依赖 build-politics.py 的解析逻辑（同目录）。
"""
import json
import re
import shutil
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

bp = SourceFileLoader('bp', str(Path(__file__).parent / 'build-politics.py')).load_module()
mt = SourceFileLoader('mt', str(Path(__file__).parent / 'politics-material.py')).load_module()

SITE = bp.SITE

NAV = """<nav class="sitebar" aria-label="站点导航">
  <a class="sb-brand" href="/">考研资料总库</a>
  <div class="sb-links">
    <a href="/math/">数学真题</a>
    <a href="/exam/">英语真题</a>
    <a href="/politics/" class="on">政治真题</a>
    <a href="/english/">英语速查</a>
    <a href="/library/">知识库</a>
  </div>
</nav>"""

HEAD = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{desc}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@600;700&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
<link rel="stylesheet" href="/site.css">
<link rel="stylesheet" href="/exam/exam.css">
<link rel="stylesheet" href="/politics/politics.css">
</head>
<body>"""

TAIL = """</body>
</html>"""

SECTION_META = {
    'single': ('一', '单项选择', '单项选择题', 16,
               '1 — 16 小题，每小题 1 分，共 16 分。下列每题给出的四个选项中，只有一个选项是符合题目要求的。'),
    'multi': ('二', '多项选择', '多项选择题', 34,
              '17 — 33 小题，每小题 2 分，共 34 分。下列每题给出的四个选项中，至少有两个选项是符合题目要求的。多选、少选、错选均不得分。'),
    'essay': ('三', '材料分析', '材料分析题', 50,
              '34 — 38 小题，每小题 10 分，共 50 分。要求结合所学知识分析材料并回答问题。'),
}


MARK = re.compile(r'^(材料\s*[0-9一二三四五六]|摘编自|摘自)')
QSUB = re.compile(r'^[(（]\s*[0-9]\s*[)）]')
NOISE = re.compile(r'^(答案速查|参考答案|答案与解析|【答案)')


def merge_paras(lines):
    """分析题：把 OCR 的折行合并成自然段（材料标头单独成段，小问整段不断开）"""
    out, buf, in_q = [], '', False
    for raw in lines:
        ln = raw.strip()
        if not ln or NOISE.match(ln):
            continue
        if MARK.match(ln):
            if buf:
                out.append(buf)
            out.append(ln)
            buf, in_q = '', False
            continue
        if QSUB.match(ln):
            if buf:
                out.append(buf)
            buf, in_q = ln, True
            continue
        buf += ln
        if not in_q and len(buf) >= 100 and ln[-1] in '。？！':
            out.append(buf)
            buf = ''
    if buf:
        out.append(buf)
    return out


OFFSET = {'single': 1, 'multi': 17, 'essay': 34}   # 全卷连续编号：1—16 / 17—33 / 34—38


DUP_Q = re.compile(r'^[(（]\s*\d\s*[)）][^？?]{4,220}[？?](?:\s*[（(]\s*\d+\s*分\s*[)）])?')

JUNK_INLINE = re.compile(
    r'[\[【（(]\s*(?:分数|选项|考点|解析|考点点拨|命题分析|答案要点)\s*[\]】）)]\s*\d*')

# 解析册里的背诵口诀/万能表格注释（2024—2026 苏一版），不属于答案正文
NOTE_JUNK = re.compile(r'【[^】]{0,60}(?:苏一|万能|背诵|表格)[^】]{0,60}】|[（(]\s*万能[^）)]{0,20}[）)]')


def scrub(s):
    """清掉混进正文的排版标记（【分数】10、【选项】…）"""
    return NOTE_JUNK.sub('', JUNK_INLINE.sub('', s or '')).strip()


PAGE_NO_TAIL = re.compile(r'(?<=[。？?！!）)》」』】])第$')


def dedupe_page_no(ps):
    """去掉页脚残字：「第」单独成段，或段落尾巴挂着一个「第」"""
    out = []
    for p in ps:
        p = PAGE_NO_TAIL.sub('', p).strip()
        if not p or re.fullmatch(r'第\s*\d{0,3}', p):
            continue
        out.append(p)
    return out


def clean_ans(ans, paras):
    """参考答案：去掉「略」「【分数】」这类占位，剥掉与题干重复的小问"""
    body = re.sub(r'\s+', '', ''.join(paras))
    out = []
    for p in ans:
        p = NOISE.sub('', p).strip()
        p = re.sub(r'^略\s*', '', p).strip()
        p = scrub(p)
        if not p:
            continue
        m = DUP_Q.match(p)
        if m and re.sub(r'\s+', '', m.group(0))[:18] in body:
            p = p[m.end():].strip()
        if p:
            out.append(p)
    return out


def to_paper(sections, year=None):
    out = []
    for kind in ('single', 'multi', 'essay'):
        src = next((s for s in sections if s['kind'] == kind and s['questions']), None)
        if not src:
            continue
        lbl, nav, title, pts, direction = SECTION_META[kind]
        if kind == 'essay':
            qs = []
            for q in src['questions']:
                # 合并成段后再跑一次 fix_text：有些错字被折行拆开（「地」+「苺」），逐行替换匹配不到
                paras = dedupe_page_no([x for x in (scrub(bp.fix_text(p)) for p in merge_paras(q.get('lines') or [q['stem']])) if x])
                n = q['n'] + OFFSET[kind] - 1
                # 源文件只有小问、缺材料时（2026 苏一版），把人工录入的材料接在题干行后面
                mat = mt.MATERIAL.get(year, {}).get(n) if year else None
                if mat:
                    cleaned = [bp.fix_text(bp.norm(p)) for p in mat]
                    head = [paras[0]] if paras and paras[0].startswith('结合材料') else []
                    rest = paras[1:] if head else paras
                    paras = head + cleaned + rest
                qs.append({'n': n,
                           'paras': paras,
                           'ans': dedupe_page_no([bp.fix_text(p) for p in clean_ans(merge_paras(q.get('ans') or []), paras)])})
        else:
            qs = [{'n': q['n'] + OFFSET[kind] - 1, 'stem': scrub(bp.fix_text(q['stem'])),
                   'options': [scrub(bp.fix_text(q['options'].get(k, ''))) for k in 'ABCD'],
                   'answer': q['answer']} for q in src['questions']]
        out.append({'id': kind, 'kind': kind, 'label': lbl, 'nav': nav, 'title': title,
                    'points': pts, 'direction': direction, 'questions': qs})
    return out


def ex_bar(year, self_href=None):
    """顶部条：年份 + 练习记录 / 一页纸（和数学真题一致，进来就是试卷）"""
    chips = []
    for y in sorted(bp.PAPERS, reverse=True):
        cur = y == year
        href = self_href if (cur and self_href) else f'/politics/{y}'
        cls = ' on' if cur else ''
        aria = ' aria-current="page"' if cur else ''
        chips.append(f'<a class="eb-yr{cls}" href="{href}"{aria} data-id="{y}" title="{y} 年考研政治真题">{y}</a>')
    return ('<div class="ex-bar"><div class="ex-bar-in">'
            f'<div class="eb-years" aria-label="年份">{"".join(chips)}</div>'
            '<div class="eb-side"><a class="eb-link" href="/politics/records.html">练习记录</a>'
            '<a class="eb-link" href="/library/政治/">政治一页纸</a></div>'
            '</div></div>')


MARKS_JS = """<script>
(function () {
  [].forEach.call(document.querySelectorAll('.eb-yr[data-id]'), function (a) {
    try {
      var s = JSON.parse(localStorage.getItem('kaoyan-politics:' + a.dataset.id) || '{}');
      var n = Object.keys(s.picks || {}).length;
      if (n) { a.classList.add('has'); a.title = a.title + ' · 已答 ' + n + ' 题'; }
    } catch (e) {}
  });
})();
</script>"""

# 首页 = 入口：记住上次打开的年份，从别的板块切回来时直接跳过去（显式点年份不受影响）
POS_JS = """<script>
(function(){try{
  var p=JSON.parse(localStorage.getItem('kaoyanPolitics.position.v1')||'null');
  var y=p&&p.y;
  if(typeof y==='number'&&y>=2010&&y<=2026&&y!==%d){
    location.replace('/politics/'+y);
  }
}catch(e){}})();
</script>"""


def emit(year, sections, out_name=None):
    plist = to_paper(sections, year)
    mc = sum(len(s['questions']) for s in plist if s['kind'] in ('single', 'multi'))
    total = sum(len(s['questions']) for s in plist)
    missing = sum(1 for s in plist if s['kind'] in ('single', 'multi')
                  for q in s['questions'] if not q['answer'])

    data_dir = SITE / 'politics/data'
    data_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = SITE / 'pdfs/politics'
    pdf_dir.mkdir(parents=True, exist_ok=True)

    paper_src, sol_src = bp.PAPERS[year]
    shutil.copyfile(bp.SRC / paper_src, pdf_dir / f'{year}.pdf')
    shutil.copyfile(bp.SRC / sol_src, pdf_dir / f'{year}-sol.pdf')

    paper = {
        'id': str(year),
        'year': year,
        'title': f'{year} 年考研政治真题',
        'kicker': f'Politics · {year}',
        'meta': [f'{total} 题', '满分 100 分', '建议 180 分钟'],
        'paper': f'/pdfs/politics/{year}.pdf',
        'sol': f'/pdfs/politics/{year}-sol.pdf',
        'sections': plist,
    }
    (data_dir / f'{year}.js').write_text(
        'window.__PPAPER__ = ' + json.dumps(paper, ensure_ascii=False, indent=1) + ';\n',
        encoding='utf-8')

    papers_js = json.dumps([{'id': y, 'y': y} for y in sorted(bp.PAPERS)], ensure_ascii=False)
    html = HEAD.format(title=f'{year} 年考研政治真题 · 考研资料总库',
                       desc=f'{year} 年考研政治真题逐题还原：单选、多选、材料分析题，可在线作答并自动算分。')
    if out_name == 'index.html':
        html = html.replace('</head>', POS_JS % year + '\n</head>')
    html += '\n' + NAV + '\n'
    html += ex_bar(year, SELF_HREF[0]) + '\n'
    html += '<div id="paper"></div>\n'
    html += MARKS_JS + '\n'
    html += f'<script>window.__PAPERS__ = {papers_js};</script>\n'
    html += f'<script src="/politics/data/{year}.js"></script>\n'
    html += '<script src="/politics/politics.js"></script>\n'
    html += TAIL
    (SITE / 'politics' / (out_name or f'{year}.html')).write_text(html, encoding='utf-8')
    return total, mc, missing


SELF_HREF = [None]   # 生成 index.html 时传出 "/politics/"，让当前年份 chip 指向首页


RECORDS_BODY = """
<div class="ex-wrap">
  <header class="ex-mast">
    <div class="ex-seal" aria-hidden="true">政</div>
    <div class="ex-mast-main">
      <p class="kicker">Records · Local Only</p>
      <h1>我的练习记录</h1>
      <p class="ex-sub">
        <span>客观题满分 50</span>
        <span>单选 1 分 · 多选 2 分</span>
        <span>只保存在这台设备的浏览器里</span>
      </p>
    </div>
  </header>
  <section class="my-stats" id="myStats"></section>
</div>
<script src="/politics/pstats.js"></script>
"""


def emit_records():
    html = HEAD.format(title='我的练习记录 · 考研政治真题',
                       desc='考研政治真题作答记录：各卷客观题得分、正确率与作答进度，保存在本机浏览器。')
    html += '\n' + NAV + '\n' + ex_bar(None, None) + RECORDS_BODY + TAIL
    (SITE / 'politics/records.html').write_text(html, encoding='utf-8')


def emit_index(info):
    """首页直接显示最新一年的整卷（不再有年份列表中转页）"""
    years = sorted((k for k in info if isinstance(k, int)), reverse=True)
    latest = years[0]
    total_q = sum(info[y]['total'] for y in years)
    SELF_HREF[0] = '/politics/'
    emit(latest, info['_sections'][latest], 'index.html')
    SELF_HREF[0] = None
    emit_records()
    print(f'✓ /politics/index.html = {latest} 年整卷（{len(years)} 套 / {total_q} 题），records.html 已生成')


if __name__ == '__main__':
    args = [int(a) for a in sys.argv[1:] if a.isdigit()]
    years = args or sorted(bp.PAPERS)
    info = {'_sections': {}}
    for y in years:
        sections, mc, miss, bad = bp.build(y)
        total, nmc, nmiss = emit(y, sections)
        info[y] = {'total': total}
        info['_sections'][y] = sections
        flag = '' if not nmiss else f'  ⚠ 缺答案 {nmiss}'
        print(f'{y}: {total} 题（客观 {nmc}）{flag}', flush=True)
    if not args:
        emit_index(info)
