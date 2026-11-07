#!/usr/bin/env python3
"""从「无水印」原卷 PDF 重切英语作文配图（Part B 漫画 / 图表）。

为什么需要它：网站上的配图是从原卷 PDF 里裁出来的图片，早先手动裁的几张
框选偏了（2021 英语一顶部对话框被切、2019 英语二横轴标签被切）。
这里按「先找整页里最大的图形块，再按墨迹收紧」的规则重切，绝大多数卷
可以自动完成；版式特殊的六张用 OVERRIDE 里的固定框。

用法：
    python3 build-writing-figs.py            # 只打印每张会切成什么样，不落盘
    python3 build-writing-figs.py --apply     # 写进 kaoyan-hub/exam/figs/writing/
    python3 build-writing-figs.py --apply 2021-y1 2024-y1   # 只重做指定几份

依赖：pip install pymupdf pillow
源目录：DEFAULT_SRC，可用环境变量 CLEAN_PDF_DIR 覆盖（每年一个 PDF）。
"""
import os
import sys

import numpy as np
import pymupdf
from PIL import Image

DEFAULT_SRC = os.path.expanduser('~/Desktop/考研英语资料/考研真题（无水印）')
SRC = os.environ.get('CLEAN_PDF_DIR', DEFAULT_SRC)
HUB = os.path.expanduser('~/File_no_iCloud/kaoyan-website/kaoyan-hub')
OUT = os.path.join(HUB, 'exam/figs/writing')
DPI = 200

# 版式特殊、自动判定会跑偏的卷：整页坐标（100dpi 下的像素框）→ 在该框内按墨迹收紧
OVERRIDE = {
    '2012-y2': (14, (140, 575, 615, 875)),
    '2021-y1': (14, (200, 668, 470, 935)),
    '2022-y1': (14, (195, 540, 580, 850)),
    '2023-y2': (14, (155, 280, 630, 585)),
    '2024-y1': (14, (100, 706, 700, 1030)),
    '2025-y1': (14, (140, 820, 700, 1035)),
    '2021-y2': (14, (150, 620, 575, 925)),
    '2026-y2': (14, (215, 693, 580, 950)),
}


def clean_pdf(pid):
    """2006—2009 英语一用通用的《N年考研英语真题》，其余按科目分目录。"""
    year, part = pid.split('-')
    if part == 'y1':
        p = os.path.join(SRC, '英语一', f'{year}年考研英语真题.pdf')
        return p if os.path.exists(p) else os.path.join(SRC, '英语一', f'{year}年考研英语一真题.pdf')
    return os.path.join(SRC, '英语二', f'{year}年考研英语二真题.pdf')


def render(page, dpi):
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def bands(arr, gap=30, thresh=205):
    """按「整行为空白」把页面切成横条，间隔小于 gap 的合并（一段正文会被并成一条）。"""
    ink = arr < thresh
    rows = ink.any(1)
    raw, start = [], None
    for i, v in enumerate(rows):
        if v and start is None:
            start = i
        elif not v and start is not None:
            raw.append([start, i])
            start = None
    if start is not None:
        raw.append([start, len(rows)])
    merged = []
    for b in raw:
        if merged and b[0] - merged[-1][1] < gap:
            merged[-1][1] = b[1]
        else:
            merged.append(b)
    return merged


def ink_box(arr, y0, y1, x0=0, x1=None, thresh=205):
    x1 = arr.shape[1] if x1 is None else x1
    sub = arr[y0:y1, x0:x1]
    ys, xs = np.where(sub < thresh)
    if len(ys) == 0:
        return None
    return int(x0 + xs.min()), int(y0 + ys.min()), int(x0 + xs.max()) + 1, int(y0 + ys.max()) + 1


def find_figure_page(doc):
    """写作是最后一节，从后往前找第一张有整块大图形的页。"""
    for i in range(doc.page_count - 1, -1, -1):
        arr = render(doc[i], 100)
        h = arr.shape[0]
        for s, e in bands(arr, gap=18):
            if (e - s) > h * 0.12 and s > h * 0.2:
                return i
    return doc.page_count - 1



def trim_prompt_lines(arr, y0, y1, thresh=205):
    """提示语和图片挨得近时会被并进同一块：从块顶连续 2 行以上的整行文字视为提示语，跳过。"""
    ink = arr[y0:y1] < thresh
    rows = ink.any(1)
    runs, start = [], None
    for i, v in enumerate(rows):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(rows)))
    width = arr.shape[1]
    n = 0
    for s, e in runs:
        band = ink[s:e]
        cols = np.where(band.any(0))[0]
        span = (cols.max() - cols.min() + 1) / width if len(cols) else 0
        if 8 <= (e - s) <= 34 and span > 0.55 and band.mean() > 0.10:
            n += 1
        else:
            break
    if n >= 2 and n < len(runs):
        return y0 + runs[n][0]
    return y0

def crop_auto(doc, pno):
    page = doc[pno]
    arr = render(page, DPI)
    h, w = arr.shape
    content = [b for b in bands(arr, gap=30) if not (b[0] < h * 0.10 and b[1] < h * 0.18)]
    footer = [b for b in content if b[0] > h * 0.86]
    bottom = footer[0][0] if footer else int(h * 0.96)
    content = [b for b in content if b[0] <= bottom]
    cands = [b for b in content if (b[1] - b[0]) > h * 0.08] or content
    if not cands:
        return None
    fig = cands[-1]      # 配图是正文里最后一个大块（下面就是页脚）
    # 提示语和图片贴得很近时会被并成一块，这里在块内按小间距再切一次，取最高的子块
    inner = bands(arr[fig[0]:fig[1]], gap=14)
    if len(inner) > 1:
        sub = max(inner, key=lambda b: b[1] - b[0])
        fig = [fig[0] + sub[0], fig[0] + sub[1]]
    box = ink_box(arr, fig[0], bottom)
    if not box:
        return None
    return box, 14


def crop_override(doc, pno, box100):
    arr = render(doc[pno], DPI)
    x0, y0, x1, y1 = [int(v * 2) for v in box100]
    box = ink_box(arr, y0, y1, x0, x1)
    if not box:
        return None
    return box, 16


def build(pid, apply=False):
    doc = pymupdf.open(clean_pdf(pid))
    if pid in OVERRIDE:
        pno, box100 = OVERRIDE[pid]
        pno -= 1                      # 覆盖表里写的是「第几页」，转成 0 起
        got = crop_override(doc, pno, box100)
        how = 'override'
    else:
        pno = find_figure_page(doc)
        got = crop_auto(doc, pno)
        how = 'auto'
    if not got:
        print(f'{pid}: 没找到图形块，跳过')
        return
    (bx0, by0, bx1, by1), margin = got
    page = doc[pno]
    pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
    im = Image.frombytes('L', (pix.width, pix.height), pix.samples)
    x0, y0 = max(0, bx0 - margin), max(0, by0 - margin)
    x1, y1 = min(pix.width, bx1 + margin), min(pix.height, by1 + margin)
    crop = im.crop((x0, y0, x1, y1))
    note = f'{pid}: p{pno + 1} {how:8s} {crop.size[0]}×{crop.size[1]}'
    if apply:
        crop.save(os.path.join(OUT, f'{pid}.png'))
        print(note + '  已写入')
    else:
        print(note)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply = '--apply' in sys.argv
    ids = args or sorted(f[:-4] for f in os.listdir(OUT) if f.endswith('.png'))
    for pid in ids:
        try:
            build(pid, apply=apply)
        except Exception as e:  # 单卷失败不影响其他卷
            print(f'{pid}: ERROR {type(e).__name__} {e}')


if __name__ == '__main__':
    main()
