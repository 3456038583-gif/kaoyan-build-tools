#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 RapidOCR 识别扫描版政治真题（无文本层的 2021-2023），结果缓存成 JSON。

用法（需在装有 rapidocr_onnxruntime 的环境下运行）：
  python ocr-politics.py 2021 2022 2023
输出：.cache/po-ocr/{year}.json  {"paper": [每页文本], "sol": [每页文本]}
"""
import json
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parent))
from importlib.machinery import SourceFileLoader  # noqa: E402

bp = SourceFileLoader('bp', str(Path(__file__).parent / 'build-politics.py')).load_module()

from rapidocr_onnxruntime import RapidOCR  # noqa: E402

OCR = RapidOCR()
OUT = Path(__file__).parent / '.cache/po-ocr'
OUT.mkdir(parents=True, exist_ok=True)


def ocr_pdf(path, dpi=400):
    doc = pymupdf.open(path)
    pages = []
    for i, pg in enumerate(doc):
        pix = pg.get_pixmap(dpi=dpi)
        img = f'/tmp/po-ocr/_p{i}.png'
        pix.save(img)
        res, _ = OCR(img)
        pages.append('\n'.join(r[1] for r in res) if res else '')
        Path(img).unlink(missing_ok=True)
        print(f'  {path.name} p{i + 1}/{doc.page_count}', flush=True)
    return pages


def main(years):
    for y in years:
        paper, sol = bp.PAPERS[y]
        print(f'== {y}', flush=True)
        data = {'paper': ocr_pdf(bp.SRC / paper), 'sol': ocr_pdf(bp.SRC / sol)}
        (OUT / f'{y}.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        print(f'  saved {y}', flush=True)


if __name__ == '__main__':
    main([int(a) for a in sys.argv[1:]])
