#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""刷新政治板块的顶部条（可重复执行）。

改动要点：
  1. 「政治真题」与「肖八模拟」并列为左侧两个板块标签，不再是「真题 + 右侧工具链接」；
  2. 进入肖八页面时，年份行换成 卷一…卷八，八套卷各有入口；
  3. 右侧只留真正的工具：成绩台账 / 练习记录 / 政治一页纸。

用法：python3 build-tools/patch-politics-bars.py
"""

import pathlib
import re
import sys

SITE = pathlib.Path(__file__).resolve().parents[1] / 'kaoyan-hub'
OUT = SITE / 'politics'

YEARS = list(range(2026, 2009, -1))
SETS = ['一', '二', '三', '四', '五', '六', '七', '八']

BAR_START = '<div class="pbar">'
BAR_END = '</div></div></div></div>'


def chip(label, count, href, on, aria=False):
    cls = 'pmod on' if on else 'pmod'
    cur = ' aria-current="page"' if aria else ''
    return f'<a class="{cls}" href="{href}"{cur}>{label}<span class="cnt">{count}</span></a>'


def tool(label, href, active=False):
    cls = 'pmod pmod--tool is-active' if active else 'pmod pmod--tool'
    cur = ' aria-current="page"' if active else ''
    return f'<a class="{cls}" href="{href}"{cur}>{label}</a>'


def year_row(cur_year):
    out = []
    for y in YEARS:
        on = ' on' if y == cur_year else ''
        cur = ' aria-current="page"' if y == cur_year else ''
        href = f'/politics/{y}'
        out.append(
            f'<a class="pyear{on}" href="{href}"{cur} data-id="{y}" data-n="38" '
            f'title="{y} 年考研政治真题">{y}<span class="y-st">38 题</span></a>'
        )
    return ''.join(out)


def set_row(cur_set):
    out = []
    for i, cn in enumerate(SETS, start=1):
        on = ' on' if cur_set == i else ''
        cur = ' aria-current="page"' if cur_set == i else ''
        out.append(
            f'<a class="pyear{on}" href="/politics/xiao8-{i}"{cur} data-id="xiao8-{i}" data-n="38" '
            f'title="2027 肖秀荣八套卷（{cn}）">卷{cn}<span class="y-st">38 题</span></a>'
        )
    return ''.join(out)


def build_bar(kind, cur, tool_act):
    """kind: 'year' | 'xiao8'；cur：当前年份或套卷号；tool_act：'scores'/'records'/None"""
    on_year = kind == 'year'
    on_set = kind == 'xiao8'

    sec_pol = chip('政治真题', '17 套', '/politics/', on_year, aria=on_year and kind == 'year' and cur is not None)
    sec_x8 = chip(
        '肖八模拟', '8 套',
        f'/politics/xiao8-{cur}' if on_set else '/politics/xiao8-1',
        on_set, aria=on_set,
    )

    tools = (
        tool('成绩台账', '/politics/scores', tool_act == 'scores')
        + tool('练习记录', '/politics/records.html', tool_act == 'records')
        + tool('<span class="t-lg">政治</span>一页纸', '/library/政治/')
    )

    years = set_row(cur) if on_set else year_row(cur if on_year else None)
    label = '套卷' if on_set else '年份'

    return (
        f'{BAR_START}<div class="pbar-in">'
        f'<div class="pmods" aria-label="板块">'
        f'<div class="pmodgroup">{sec_pol}{sec_x8}</div>'
        f'<div class="pmodgroup pmodgroup--tools">{tools}</div>'
        f'</div>'
        f'<div class="pbar-years"><div class="pyears" aria-label="{label}">{years}</div></div>'
        f'</div></div>'
    )


def current_page(name: str):
    """返回 (kind, cur, tool_act)"""
    if name.startswith('xiao8-'):
        try:
            return 'xiao8', int(name.split('-')[1].split('.')[0]), None
        except ValueError:
            return 'xiao8', 1, None
    if name == 'records.html':
        return 'year', None, 'records'
    if name == 'scores.html':
        return 'year', None, 'scores'
    if name == 'index.html':
        return 'year', 2026, None
    m = re.fullmatch(r'(20\d{2})\.html', name)
    if m:
        return 'year', int(m.group(1)), None
    return None, None, None


def main():
    changed = 0
    skipped = []
    for p in sorted(OUT.glob('*.html')):
        kind, cur, tool_act = current_page(p.name)
        if kind is None:
            skipped.append(p.name)
            continue

        s = p.read_text(encoding='utf-8')
        i = s.find(BAR_START)
        if i < 0:
            skipped.append(p.name + '(无板块条)')
            continue
        j = s.find(BAR_END, i)
        if j < 0:
            skipped.append(p.name + '(板块条未闭合)')
            continue

        new = build_bar(kind, cur, tool_act)
        s2 = s[:i] + new + s[j + len(BAR_END):]
        if s2 != s:
            p.write_text(s2, encoding='utf-8')
            changed += 1

    print(f'已刷新 {changed} 页；跳过 {len(skipped)}：{skipped}')


if __name__ == '__main__':
    sys.exit(main())
