#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把《27 考研政治一页纸 · 知识点手册》PDF 转成保留原配色与版式的网页。

- 每个 PDF 页面渲染成一张固定版心的「纸」，文字按原始坐标绝对定位（可选中、可搜索）
- 颜色、字号、粗体全部取自 PDF 的 span 属性；底色块取自页面绘图对象
- 内嵌图片单独导出到 assets/
输出： library/政治/一页纸.html、library/政治/assets/*、library/政治/index.html
"""
import json
import shutil
from pathlib import Path
from urllib.parse import quote

import pymupdf

SRC = Path('/Users/feikntn111/Desktop/考研政治资料/澄潇宇一页纸/27考研政治一页纸-知识点手册.pdf')
SITE = Path.home() / 'File_no_iCloud/kaoyan-website/kaoyan-hub'
OUT = SITE / 'library/政治'
ASSETS = OUT / 'assets'
PDF_OUT = SITE / 'pdfs/politics/27-yiyeye.pdf'


def rgb(c):
    if c is None:
        return None
    if isinstance(c, (int, float)):
        v = int(round(c * 255))
        return f'#{v:02x}{v:02x}{v:02x}'
    if len(c) == 1:
        v = int(round(c[0] * 255))
        return f'#{v:02x}{v:02x}{v:02x}'
    r, g, b = (int(round(x * 255)) for x in c[:3])
    return f'#{r:02x}{g:02x}{b:02x}'


def esc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;'))


def font_class(name):
    n = name.lower()
    if 'song' in n or 'kai' in n or 'fangsong' in n or 'fang' in n or 'serif' in n:
        return 'f-serif'
    return 'f-sans'


def render_page(doc, pno, page_no_label):
    pg = doc[pno]
    W, H = pg.rect.width, pg.rect.height
    parts = []

    # 1) 底色块 / 色条（大块先画，小块后画，避免白底盖住彩色条）
    draws = sorted(pg.get_drawings(), key=lambda d: -(d['rect'].width * d['rect'].height))
    for dr in draws:
        r = dr['rect']
        fill = rgb(dr.get('fill'))
        stroke = rgb(dr.get('color'))
        w = r.width
        h = r.height
        if fill is None and stroke is None:
            continue
        style = [f'left:{r.x0:.1f}px', f'top:{r.y0:.1f}px',
                 f'width:{max(w, 0.8):.1f}px', f'height:{max(h, 0.8):.1f}px']
        if fill:
            style.append(f'background:{fill}')
        if stroke:
            style.append(f'border:0.6px solid {stroke}')
        if not fill and w < 1.5:
            style.append('background:currentColor')
        parts.append(f'<i class="sh-b" style="{";".join(style)}"></i>')

    # 2) 图片
    for xref, *_ in pg.get_images(full=True):
        try:
            rects = pg.get_image_rects(xref)
        except Exception:
            rects = []
        if not rects:
            continue
        pix = pymupdf.Pixmap(doc, xref)
        if pix.n - pix.alpha >= 4:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        name = f'p{pno + 1}-{xref}.png'
        if pix.width >= 8 and pix.height >= 8:
            pix.save(ASSETS / name)
            for r in rects:
                parts.append(
                    f'<img class="sh-img" src="/library/政治/assets/{name}" alt="" '
                    f'style="left:{r.x0:.1f}px;top:{r.y0:.1f}px;width:{r.width:.1f}px;height:{r.height:.1f}px">')

    # 3) 文字
    raw = pg.get_text('dict')
    for b in raw['blocks']:
        if b['type'] != 0:
            continue
        for line in b['lines']:
            dirx, diry = line.get('dir', (1, 0))
            rotated = abs(diry) > 0.01
            for sp in line['spans']:
                txt = sp['text']
                if not txt.strip():
                    continue
                color = rgb(sp['color'] if not isinstance(sp['color'], int) else
                            ((sp['color'] >> 16 & 255) / 255, (sp['color'] >> 8 & 255) / 255, (sp['color'] & 255) / 255))
                x0, y0, x1, y1 = sp['bbox']
                size = sp['size']
                weight = '600' if any(k in sp['font'].lower() for k in ('bold', 'semibold', 'medium', 'hei')) else '400'
                st = [f'left:{x0:.1f}px', f'top:{y0:.1f}px', f'font-size:{size:.1f}px',
                      f'color:{color}', f'font-weight:{weight}']
                if rotated:
                    st.append(f'transform:rotate({-diry * 57.3:.1f}deg)')
                parts.append(f'<span class="sh-t {font_class(sp["font"])}" style="{";".join(st)}">{esc(txt)}</span>')

    return (f'<section class="sheet" id="p{pno + 1}" data-p="{pno + 1}" '
            f'style="width:{W:.0f}px;height:{H:.0f}px">\n'
            f'  <div class="sheet-pad"></div>\n  ' + '\n  '.join(parts) +
            f'\n  <div class="sheet-no">{page_no_label}</div>\n</section>')


def build():
    doc = pymupdf.open(SRC)
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    for f in ASSETS.glob('*.png'):
        f.unlink()
    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, PDF_OUT)

    sheets = []
    for pno in range(doc.page_count):
        pg = doc[pno]
        if not pg.get_text().strip() and not pg.get_images() and not pg.get_drawings():
            continue  # 真正的空白页
        sheets.append(render_page(doc, pno, f'{pno + 1} / {doc.page_count}'))

    nav_chips = '\n'.join(
        f'<a href="#p{i + 1}">{i + 1:02d}</a>' for i in range(doc.page_count)
        if f'id="p{i + 1}"' in '\n'.join(sheets))

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>27 考研政治一页纸 · 知识点手册 · 知识库</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@600;700&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
<link rel="stylesheet" href="/site.css">
<link rel="stylesheet" href="/library/note.css">
<link rel="stylesheet" href="/library/政治/onepage.css">
</head>
<body class="note-page op-page">

<nav class="sitebar" aria-label="站点导航">
  <a class="sb-brand" href="/">考研资料总库</a>
  <div class="sb-links">
    <a href="/math/">数学真题</a>
    <a href="/exam/">英语真题</a>
    <a href="/politics/">政治真题</a>
    <a href="/english/">英语速查</a>
    <a href="/library/" class="on">知识库</a>
  </div>
</nav>

<div class="op-wrap">
  <header class="op-head">
    <nav class="crumbs"><a href="/library/">知识库</a> <span class="sep">/</span> <a href="/library/政治/">政治</a> <span class="sep">/</span> <span>一页纸</span></nav>
    <h1>27 考研政治一页纸 · 知识点手册</h1>
    <p class="op-sub">澄潇宇一页纸 · {len(sheets)} 页 · 按原版配色与版式还原，文字可选中、可检索</p>
    <div class="op-actions">
      <a class="op-btn solid" href="/pdfs/politics/27-yiyeye.pdf" target="_blank" rel="noopener">打开原版 PDF ↗</a>
      <a class="op-btn" href="/pdfs/politics/27-yiyeye.pdf" download>下载 PDF</a>
      <a class="op-btn" href="/politics/">配套真题练习</a>
      <button class="op-btn" type="button" id="zoomBtn">放大</button>
    </div>
    <div class="op-pages" id="opPages">
      <span class="op-pages-lbl">页码</span>
{nav_chips}
    </div>
  </header>

  <main class="op-body" id="opBody">
{''.join(sheets)}
  </main>

  <footer class="op-foot">
    <p>内容与配色取自《27 考研政治一页纸 · 知识点手册》原文档，仅供复习查阅。</p>
    <p><a href="/pdfs/politics/27-yiyeye.pdf" target="_blank" rel="noopener">原版 PDF</a> · <a href="/library/">返回知识库</a></p>
  </footer>
</div>

<script src="/library/政治/onepage.js"></script>
</body>
</html>
"""
    (OUT / '一页纸.html').write_text(html, encoding='utf-8')
    (OUT / 'onepage.css').write_text(CSS, encoding='utf-8')
    (OUT / 'onepage.js').write_text(JS, encoding='utf-8')
    index_html = INDEX_HTML.replace('__PDF__', '/pdfs/politics/27-yiyeye.pdf')
    (OUT / 'index.html').write_text(index_html, encoding='utf-8')
    print(f'✓ 一页纸：{len(sheets)} 页 → {OUT}')


CSS = """/* 一页纸手册 · 原版版式还原 */
.op-page { background: var(--paper); }
.op-wrap { max-width: 1120px; margin: 0 auto; padding: 0 20px 80px; }
.op-head { padding: 26px 0 14px; border-bottom: 1px solid var(--line); margin-bottom: 18px; }
.crumbs { font-size: 12px; color: var(--muted); margin-bottom: 10px; }
.crumbs a:hover { color: var(--accent); }
.crumbs .sep { margin: 0 6px; opacity: .6; }
.op-head h1 { margin: 0; font-family: var(--serif); font-size: clamp(22px, 3vw, 30px); letter-spacing: .03em; }
.op-sub { margin: 8px 0 14px; font-size: 13px; color: var(--muted); }
.op-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.op-btn {
  appearance: none; cursor: pointer; font-size: 12.5px;
  padding: 7px 13px; border-radius: 5px; border: 1px solid var(--line);
  background: var(--surface); color: var(--muted); transition: all .15s;
}
.op-btn:hover { color: var(--accent); border-color: var(--accent); }
.op-btn.solid { background: #98521c; border-color: #98521c; color: #fff; }
.op-btn.solid:hover { filter: brightness(1.08); color: #fff; }
.op-pages {
  display: flex; flex-wrap: wrap; gap: 5px; align-items: center;
  margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--line);
}
.op-pages-lbl { font-size: 11.5px; color: var(--muted); margin-right: 4px; }
.op-pages a {
  font-family: var(--mono); font-size: 11px; color: var(--muted);
  border: 1px solid var(--line); border-radius: 3px; padding: 2px 6px;
}
.op-pages a:hover { color: var(--accent); border-color: var(--accent); }

.op-body { display: flex; flex-direction: column; gap: 26px; align-items: center; }
.sheet {
  position: relative; flex: none;
  background: #fff; color: #000;
  box-shadow: 0 1px 2px rgba(30, 25, 15, .1), 0 12px 30px -18px rgba(30, 25, 15, .45);
  border: 1px solid #e7e3d8; border-radius: 2px;
  transform-origin: top center;
  overflow: hidden;
}
.op-body.zoomed { align-items: flex-start; overflow-x: auto; }
.sheet-pad { position: absolute; inset: 0; pointer-events: none; }
.sh-b { position: absolute; display: block; }
.sh-img { position: absolute; display: block; }
.sh-t {
  position: absolute; white-space: pre; line-height: 1;
  font-kerning: none; letter-spacing: 0;
  transform-origin: left top;
}
.sh-t.f-sans { font-family: "Noto Sans SC", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; }
.sh-t.f-serif { font-family: "Noto Serif SC", "Songti SC", "STSong", "SimSun", serif; }
.sheet-no {
  position: absolute; right: 10px; bottom: 6px;
  font-family: var(--mono); font-size: 9px; color: #b9b3a4;
}
.op-foot { margin-top: 34px; padding-top: 14px; border-top: 1px solid var(--line); font-size: 12px; color: var(--muted); }
.op-foot a { border-bottom: 1px solid var(--line); }

@media (max-width: 720px) {
  .op-wrap { padding: 0 12px 60px; }
  .op-head h1 { font-size: 21px; }
}
"""

JS = """/* 一页纸：按容器宽度缩放每一页，保证小屏也能看全 */
(function () {
  var sheets = [].slice.call(document.querySelectorAll('.sheet'));
  var body = document.getElementById('opBody');
  var zoomed = false;
  function fit() {
    if (zoomed) { sheets.forEach(function (s) { s.style.transform = 'none'; }); return; }
    var w = body.clientWidth;
    sheets.forEach(function (s) {
      var base = parseFloat(s.style.width) || s.offsetWidth;
      var k = Math.min(1, w / base);
      s.style.transform = 'scale(' + k + ')';
      s.style.height = (base ? parseFloat(s.getAttribute('data-h') || 0) : 0) + 'px';
    });
  }
  /* 缩放后父容器高度要跟着变，否则会留白/重叠 */
  function sectionH(s) {
    var h = parseFloat(s.style.height) || s.offsetHeight;
    return h;
  }
  function relayout() {
    var w = body.clientWidth;
    sheets.forEach(function (s) {
      if (!s.dataset.w) {
        s.dataset.w = s.style.width;
        s.dataset.h = s.style.height;
      }
      var bw = parseFloat(s.dataset.w), bh = parseFloat(s.dataset.h);
      var k = zoomed ? 1 : Math.min(1, w / bw);
      s.style.width = bw + 'px';
      s.style.transform = 'scale(' + k + ')';
      s.style.marginBottom = (k < 1 ? -(bh * (1 - k)) : 0) + 'px';
    });
  }
  document.getElementById('zoomBtn').addEventListener('click', function () {
    zoomed = !zoomed;
    body.classList.toggle('zoomed', zoomed);
    this.textContent = zoomed ? '适应宽度' : '放大';
    relayout();
  });
  window.addEventListener('resize', relayout);
  relayout();
})();
"""

INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>政治 · 知识库</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@600;700&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
<link rel="stylesheet" href="/site.css">
<link rel="stylesheet" href="/library/note.css">
</head>
<body class="lib-index">

<nav class="sitebar" aria-label="站点导航">
  <a class="sb-brand" href="/">考研资料总库</a>
  <div class="sb-links">
    <a href="/math/">数学真题</a>
    <a href="/exam/">英语真题</a>
    <a href="/politics/">政治真题</a>
    <a href="/english/">英语速查</a>
    <a href="/library/" class="on">知识库</a>
  </div>
</nav>
<div class="lib-wrap">
  <header class="lib-mast">
    <div class="lib-seal">政</div>
    <div>
      <p class="lib-kicker">POLITICS LIBRARY</p>
      <h1>政治知识库</h1>
      <p class="lib-sub">1 份手册 · 27 考研政治一页纸 · 35 页知识点浓缩</p>
    </div>
  </header>

  <div class="lib-tabs" role="tablist" aria-label="科目">
    <a class="lib-tab" href="/library/">数学</a>
    <a class="lib-tab" href="/library/#english">英语</a>
    <a class="lib-tab on" href="/library/政治/" aria-current="page">政治</a>
  </div>

  <section class="lib-col">
    <h2>政治笔记<small>1 篇</small></h2>
    <ul class="plain">
      <li><a href="/library/政治/一页纸.html"><span class="li-title">27 考研政治一页纸 · 知识点手册</span><span class="badge">基础知识</span></a></li>
    </ul>
  </section>

  <section class="lib-col">
    <h2>原始资料<small>PDF</small></h2>
    <ul class="plain">
      <li><a href="__PDF__" target="_blank" rel="noopener"><span class="li-title">27 考研政治一页纸 · 知识点手册（原版 PDF）</span><span class="badge">PDF</span></a></li>
    </ul>
  </section>

  <footer class="lib-foot">
    <p>手册内容与配色取自原文档，网页版仅供检索与快速翻阅。</p>
    <p><a href="/library/">返回知识库</a> · <a href="/politics/">政治真题练习</a></p>
  </footer>
</div>
</body>
</html>
"""

def sync_search():
    """把一页纸并入知识库搜索索引（/library/search.json），重复执行不会叠加"""
    page = OUT / '一页纸.html'
    idx = SITE / 'library/search.json'
    if not (page.exists() and idx.exists()):
        return
    import re as _re
    raw = page.read_text(encoding='utf-8')
    raw = _re.sub(r'<script[\s\S]*?</script>', ' ', raw, flags=_re.I)
    raw = _re.sub(r'<style[\s\S]*?</style>', ' ', raw, flags=_re.I)
    raw = _re.sub(r'<[^>]+>', ' ', raw)
    raw = _re.sub(r'&nbsp;|&amp;|&lt;|&gt;', ' ', raw)
    raw = _re.sub(r'\s+', ' ', raw).strip()
    items = json.loads(idx.read_text(encoding='utf-8'))
    items = [x for x in items if x.get('u') != '/library/政治/一页纸.html']
    items.append({
        't': '27 考研政治一页纸 · 知识点手册',
        'u': '/library/政治/一页纸.html',
        'p': '政治/一页纸',
        'g': '政治',
        'y': '基础知识',
        'k': '政治 一页纸 知识点',
        'a': '',
        'h': '考研政治 一页纸 知识点手册 马原 毛中特 史纲 思修 时政',
        'x': raw[:3000],
    })
    idx.write_text(json.dumps(items, ensure_ascii=False), encoding='utf-8')
    print(f'✓ 搜索索引已并入一页纸（{len(items)} 条）')


if __name__ == '__main__':
    build()
    sync_search()
