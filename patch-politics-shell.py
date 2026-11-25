#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 /politics/ 已有页面刷成新外壳（板块标签在年份之上 + 统一主题色 + PDF 先预览）。

build-politics-site.py 需要从原始 PDF 重新解析，源文件不在时跑不动；
这个脚本只改 head / 导航 / 顶部条 / PDF 脚本，不碰题面数据，随时可重复执行。

用法：python3 patch-politics-shell.py
"""
import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / 'kaoyan-hub'
POL = SITE / 'politics'
VER = '20261126a'

NAV_ITEM = '<a href="/english/">英语速查</a>\n    '

# 政治页的顶部条始终是单独一行（旧版 ex-bar / 新版 pbar 都一样），整体换掉即可
BAR_RE = re.compile(r'<div class="(?:ex-bar|pbar)">.*\n')
CUR_RE = re.compile(r'class="(?:eb-yr|pyear) on"[^>]*?href="([^"]*)"[^>]*?data-id="(\d+)"')
ANY_YEAR_RE = re.compile(r'class="(?:eb-yr|pyear)[^"]*"[^>]*?data-id="(\d+)"')


def bar_html(years, cur_year, cur_href, active_tool=''):
    chips = []
    for y in sorted(years, reverse=True):
        cur = y == cur_year
        href = cur_href if (cur and cur_href) else f'/politics/{y}'
        cls = 'pyear on' if cur else 'pyear'
        aria = ' aria-current="page"' if cur else ''
        chips.append(
            f'<a class="{cls}" href="{href}"{aria} data-id="{y}" data-n="38" '
            f'title="{y} 年考研政治真题">{y}<span class="y-st">38 题</span></a>'
        )

    def tool(href, label, key):
        cls = 'pmod pmod--tool' + (' is-active' if key == active_tool else '')
        return f'<a class="{cls}" href="{href}">{label}</a>'

    return (
        '<div class="pbar"><div class="pbar-in">'
        '<div class="pmods" aria-label="板块">'
        '<div class="pmodgroup">'
        f'<a class="pmod on" href="/politics/" aria-current="page">政治真题<span class="cnt">{len(years)} 套</span></a>'
        '</div>'
        '<div class="pmodgroup pmodgroup--tools">'
        + tool('/politics/scores', '成绩台账', 'scores')
        + tool('/politics/xiao8-1', '肖八模拟', 'xiao8')
        + tool('/politics/records.html', '练习记录', 'records')
        + tool('/library/政治/', '政治一页纸', 'sheet')
        + '</div>'
        '</div>'
        '<div class="pbar-years"><div class="pyears" aria-label="年份">'
        + ''.join(chips) +
        '</div></div>'
        '</div></div>\n'
    )


# 各页高亮哪个工具（页面本身就是那个工具）
ACTIVE = {
    'scores.html': 'scores',
    'records.html': 'records',
    'xiao8-1.html': 'xiao8',
    'xiao8-2.html': 'xiao8',
    'xiao8-3.html': 'xiao8',
    'xiao8-4.html': 'xiao8',
    'xiao8-5.html': 'xiao8',
    'xiao8-6.html': 'xiao8',
    'xiao8-7.html': 'xiao8',
    'xiao8-8.html': 'xiao8',
}


def patch(p: Path) -> str:
    s = p.read_text(encoding='utf-8')
    old_bar = BAR_RE.search(s)
    if not old_bar:
        return 'skip: 没有 ex-bar'
    block = old_bar.group(0)
    years = [int(y) for y in ANY_YEAR_RE.findall(block)] or list(range(2010, 2027))
    cur = CUR_RE.search(block)
    cur_year = int(cur.group(2)) if cur else None
    cur_href = cur.group(1) if cur else None

    s = s.replace(block, bar_html(years, cur_year, cur_href, ACTIVE.get(p.name, '')), 1)
    s = s.replace('<html lang="zh-CN">', '<html lang="zh-CN" data-view="pol">', 1)
    s = s.replace('<link rel="stylesheet" href="/exam/exam.css">',
                  f'<link rel="stylesheet" href="/exam/exam.css?v={VER}">\n'
                  f'<link rel="stylesheet" href="/exam/shell.css?v={VER}">', 1)
    s = s.replace('<link rel="stylesheet" href="/politics/politics.css?v=20261121a">',
                  f'<link rel="stylesheet" href="/politics/politics.css?v={VER}">', 1)
    s = s.replace('<link rel="stylesheet" href="/politics/politics.css?v=20261122a">',
                  f'<link rel="stylesheet" href="/politics/politics.css?v={VER}">', 1)
    s = s.replace(NAV_ITEM, '', 1)
    # 旧页面里内联的「已答」标记脚本：类名跟着年份条改
    s = s.replace("document.querySelectorAll('.eb-yr[data-id]')", "document.querySelectorAll('.pyear[data-id]')")
    s = s.replace("      if (n) { a.classList.add('has'); a.title = a.title + ' · 已答 ' + n + ' 题'; }",
                  "      var st = a.querySelector('.y-st');\n"
                  "      if (n) { a.classList.add('has'); a.title = a.title + ' · 已答 ' + n + ' 题'; if (st) st.textContent = '答 ' + n; }")

    if 'pdfview.js' not in s:
        tag = f'<script src="/exam/pdfview.js?v={VER}" defer></script>\n'
        m = re.search(r'<script src="/politics/(?:data/)?[a-z0-9\-]+\.js[^"]*"></script>', s)
        if m:
            s = s[:m.start()] + tag + s[m.start():]
        else:
            s = s.replace('</body>', tag + '</body>', 1)
    p.write_text(s, encoding='utf-8')
    return f'ok（{len(years)} 个年份，当前 {cur_year or "-"}）'


def main():
    files = sorted(POL.glob('*.html'))
    for p in files:
        print(f'{p.name}: {patch(p)}')
    print(f'共 {len(files)} 个页面')


if __name__ == '__main__':
    sys.exit(main())
