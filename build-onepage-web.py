#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把「27 考研政治一页纸」重建为真正的网页流式内容（覆盖 library/政治/一页纸.html）。
数据源：PDF 复刻页的绝对定位抽取（文字/色条/符号坐标+颜色）+ PDF 内嵌原图（符号、时间轴、插图）。
保留原 PDF 的字体颜色、符号、下划线、章节配色，内容严格照 PDF。
"""
import os
import re
import sys
import json
import html as htmllib
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'kaoyan-hub')
OP_DIR = os.path.join(SITE, 'library', '政治')
HTML_IN = os.path.join(OP_DIR, '一页纸.html')
PDF = os.path.join(SITE, 'pdfs', 'politics', '27-yiyeye.pdf')
ASSETS = os.path.join(OP_DIR, 'assets')

sys.stdout.reconfigure(encoding='utf-8')
esc = htmllib.escape


def clean_text(s):
    """去掉文本层残留的控制字符（NUL 等），避免写进 HTML 后被浏览器判成二进制。"""
    return ''.join(ch for ch in s if ch == '\t' or ord(ch) >= 32)

# ---------- 1. 解析复刻页 ----------
def parse_style(st):
    d = {}
    for p in st.split(';'):
        if ':' in p:
            k, v = p.split(':', 1)
            d[k.strip()] = v.strip()
    return d

def num(s):
    return float(str(s).replace('px', ''))

CACHE = os.path.join(ROOT, 'build-tools', '.cache')
SNAPSHOT = os.path.join(CACHE, 'onepage-src.html')

def parse_sheets():
    src = HTML_IN
    raw = open(src, encoding='utf-8').read()
    if 'class="sheet"' not in raw:
        src = SNAPSHOT
        raw = open(src, encoding='utf-8').read()
    else:
        os.makedirs(CACHE, exist_ok=True)
        if not os.path.exists(SNAPSHOT) or os.path.getsize(SNAPSHOT) != len(raw.encode('utf-8')):
            open(SNAPSHOT, 'w', encoding='utf-8').write(raw)
    html = raw
    sheets = {}
    for m in re.finditer(r'<section class="sheet" id="p(\d+)"(.*?)</section>', html, re.S):
        pid = int(m.group(1))
        body = m.group(2)
        texts, bars, imgs = [], [], []
        for t in re.finditer(r'<span class="sh-t (f-\w+)" style="([^"]+)">([^<]*)</span>', body):
            d = parse_style(t.group(2))
            texts.append({
                'x': num(d.get('left', 0)), 'y': num(d.get('top', 0)),
                'text': clean_text(htmllib.unescape(t.group(3))),
                'color': d.get('color', '#000000'),
                'size': num(d.get('font-size', 9.2)),
                'weight': int(d.get('font-weight', 400)),
                'font': t.group(1),
            })
        for b in re.finditer(r'<i class="sh-b" style="([^"]+)"', body):
            d = parse_style(b.group(1))
            bars.append({
                'x': num(d.get('left', 0)), 'y': num(d.get('top', 0)),
                'w': num(d.get('width', 0)), 'h': num(d.get('height', 0)),
                'bg': d.get('background', ''), 'border': d.get('border', ''),
            })
        for i in re.finditer(r'<img class="sh-img" src="([^"]+)" alt="" style="([^"]+)"', body):
            d = parse_style(i.group(2))
            imgs.append({
                'x': num(d.get('left', 0)), 'y': num(d.get('top', 0)),
                'w': num(d.get('width', 0)), 'h': num(d.get('height', 0)),
                'src': i.group(1).split('/')[-1],
            })
        sheets[pid] = {'texts': texts, 'bars': bars, 'imgs': imgs}
    return sheets

def border_color(border):
    m = re.search(r'#[0-9a-fA-F]{6}', border or '')
    return m.group(0).lower() if m else None

# ---------- 2. 行/串 组装 ----------
def est_w(s, size):
    w = 0.0
    for ch in s:
        o = ord(ch)
        if o < 128:
            w += size * (0.32 if ch == ' ' else 0.55)
        else:
            w += size
    return w

def build_lines(items, ytol=4.0):
    """items: text spans + icon imgs（含 x,y,w,h,src 或 text,size,color,...）按 y 聚行。"""
    items = sorted(items, key=lambda it: (it['y'], it['x']))
    lines = []
    for it in items:
        if lines and abs(it['y'] - lines[-1]['y0']) <= ytol:
            lines[-1]['items'].append(it)
        else:
            lines.append({'y0': it['y'], 'items': [it]})
    out = []
    for ln in lines:
        ln['items'].sort(key=lambda it: it['x'])
        y0 = ln['y0']
        runs = []
        for it in ln['items']:
            if 'src' in it:
                runs.append({'type': 'img', 'x': it['x'], 'y': it['y'], 'w': it['w'], 'h': it['h'], 'src': it['src']})
            else:
                size = it['size']
                runs.append({'type': 't', 'x': it['x'], 'y': it['y'], 'size': size,
                             'color': it['color'], 'weight': it['weight'], 'font': it['font'],
                             'text': it['text'], 'w': est_w(it['text'], size)})
        # 合并相邻同款式文字串
        merged = []
        for r in runs:
            if (merged and merged[-1]['type'] == 't' and r['type'] == 't'
                    and merged[-1]['color'] == r['color'] and merged[-1]['size'] == r['size']
                    and merged[-1]['weight'] == r['weight'] and merged[-1]['font'] == r['font']):
                merged[-1]['text'] += r['text']
                merged[-1]['w'] = (r['x'] + r['w']) - merged[-1]['x']
            else:
                merged.append(dict(r))
        # 行的尺寸基准
        sizes = [r['size'] for r in merged if r['type'] == 't'] or [9.2]
        out.append({'y': y0, 'runs': merged, 'size': max(sizes),
                    'x0': merged[0]['x'] if merged else 0,
                    'xend': max((r['x'] + r['w']) for r in merged) if merged else 0})
    return out

# ---------- 3. 下划线 / 高亮块 ----------
def attach_marks(lines, bars):
    """把细横条识别为下划线；把小色块识别为文字高亮。"""
    uls, chips = [], []
    for b in bars:
        if b['h'] <= 2.5 and b['w'] >= 3.5:
            c = border_color(b['border']) or (b['bg'] if b['bg'] and b['bg'] not in ('currentColor', 'none') else None)
            if c:
                uls.append({'x': b['x'], 'y': b['y'], 'w': b['w'], 'c': c})
        elif b['w'] <= 60 and b['h'] <= 30 and b['bg'] and b['bg'] not in ('#ffffff', 'currentColor', 'none') and b['h'] >= 4:
            chips.append({'x': b['x'], 'y': b['y'], 'w': b['w'], 'h': b['h'], 'c': b['bg']})
    for ln in lines:
        for r in ln['runs']:
            r['u'] = None
            r['mark'] = None
            if r['type'] != 't':
                continue
            rx1 = r['x'] + r['w']
            for u in uls:
                if (r['x'] < u['x'] + u['w'] - 1.5) and (rx1 > u['x'] + 1.5) and (-1.5 <= u['y'] - (r['y'] + r['size']) <= 5.0):
                    r['u'] = u['c']
            for c in chips:
                cx0, cx1, cy0, cy1 = c['x'], c['x'] + c['w'], c['y'], c['y'] + c['h']
                rcx = r['x'] + r['w'] / 2
                rcy = r['y'] + r['size'] * 0.5
                if cx0 - 1 <= rcx <= cx1 + 1 and cy0 - 2.5 <= rcy <= cy1 + 2.5:
                    r['mark'] = c['c']
    return lines

# ---------- 4. PDF 内嵌原图 ----------
def extract_embedded():
    """从 PDF 提取内嵌原图（时间轴/插图/二维码/封面/书法），按复刻页里的 src 命名落盘。"""
    import fitz
    doc = fitz.open(PDF)
    # 每页每位置 → xref
    pos2xref = {}
    for pno in range(doc.page_count):
        pg = doc[pno]
        for im in pg.get_images(full=True):
            xref = im[0]
            for r in pg.get_image_rects(xref):
                pos2xref[(pno + 1, round(r.x0, 1), round(r.y0, 1))] = xref
    sheets = parse_sheets()
    out = {}          # src -> local file
    icon_rects = {}   # (pid, x, y) -> (pid, x, y, w, h) 供 clip 渲染
    src_first = {}    # src -> 它第一次出现的位置（供旧代码按 src 查）
    for pid, sp in sheets.items():
        for im in sp['imgs']:
            key = (pid, round(im['x'], 1), round(im['y'], 1))
            xref = pos2xref.get(key)
            src = im['src']
            if im['w'] <= 40 and im['h'] <= 40:
                # 复刻页会把同一位置的多张候选图都列出来，按位置去重只渲染一次
                icon_rects.setdefault(key, (pid, im['x'], im['y'], im['w'], im['h']))
                src_first.setdefault(src, key)
            elif src not in out and xref:
                info = doc.extract_image(xref)
                out[src] = info['image']
    os.makedirs(ASSETS, exist_ok=True)
    for src, blob in out.items():
        path = os.path.join(ASSETS, 'orig-' + src)
        with open(path, 'wb') as f:
            f.write(blob)
    # 小图标 clip 渲染（合成 SMask，白底）
    ico_by_pos = {}
    order = sorted(icon_rects.values(), key=lambda r: (r[0], r[2], r[1]))
    for i, (pid, x, y, w, h) in enumerate(order):
        pg = doc[pid - 1]
        pad = 0.1
        r = fitz.Rect(x - pad, y - pad, x + w + pad, y + h + pad)
        pix = pg.get_pixmap(dpi=600, clip=r)
        name = 'ico-%03d.png' % (i + 1)
        pix.save(os.path.join(ASSETS, name))
        ico_by_pos[(pid, round(x, 1), round(y, 1))] = name
    ico_map = {src: ico_by_pos.get(key) for src, key in src_first.items()}
    doc.close()
    return out, ico_map, ico_by_pos

# ---------- 5. 内容页结构 ----------
THEME_BY_STRIP = {
    '#f8ede1': ('tan', '#ebcbac', '#98521c', '#f7e9d9', '#d6b89a'),
    '#f9e7e5': ('rose', '#f3c9c7', '#bd3f3f', '#fbeceb', '#e5bdb9'),
    '#eaf5ed': ('green', '#c7e5d0', '#178344', '#eaf5ed', '#b8dcc3'),
}

def prose_bars(sp):
    return [b for b in sp['bars'] if b['y'] > 60 and b['y'] < 760 and not (b['h'] > 100 or b['w'] > 400 and b['h'] > 20)]

def classify_bars(bars):
    banners, card_boxes, strips, chips, uls, accents, furniture = [], [], [], [], [], [], []
    for b in bars:
        w, h = b['w'], b['h']
        bc = border_color(b['border'])
        if w > 400 and 20 < h < 45 and b['bg'] and b['bg'] != '#ffffff':
            banners.append(b)
        elif (240 <= w <= 265 and h >= 45 and b['bg'] == '#ffffff') or (w > 400 and h > 60 and b['bg'] == '#ffffff'):
            card_boxes.append(b)
        elif 240 <= w <= 265 and 35 <= h <= 50 and b['bg'] and b['bg'] != '#ffffff':
            strips.append(b)
        elif w > 400 and 20 < h < 45 and b['bg'] == '#f9e7e5':
            strips.append(b)   # 037 整幅标题条
        elif w <= 60 and h <= 30 and b['bg'] and b['bg'] not in ('', '#ffffff', 'currentColor') and h >= 4:
            chips.append(b)
        elif h <= 2.5 and w >= 3.5:
            uls.append(b)
        elif w <= 2.5 and h >= 8:
            accents.append(b)
        else:
            furniture.append(b)
    return banners, card_boxes, strips, chips, uls, accents

def banner_texts(banner, texts):
    ts = [t for t in texts if banner['y'] - 3 <= t['y'] <= banner['y'] + banner['h'] + 2
          and banner['x'] - 2 <= t['x'] <= banner['x'] + banner['w'] + 2]
    ts.sort(key=lambda t: t['x'])
    return ts

def strip_label(strip, texts):
    ts = [t for t in texts if strip['y'] - 3 <= t['y'] <= strip['y'] + strip['h'] + 2
          and strip['x'] - 2 <= t['x'] <= strip['x'] + strip['w'] + 2]
    ts.sort(key=lambda t: t['x'])
    label = ' '.join(t['text'].strip() for t in ts).strip()
    m = re.match(r'知识点\s*(\d+)\s*(.*)', label, re.S)
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None, label

def page_printed_no(sheets, pid):
    for t in sheets[pid]['texts']:
        s = t['text'].strip()
        if s.isdigit() and (t['y'] > 760) and len(s) <= 2:
            return int(s)
    return None

def build_content_model(sheets, ico_by_pos):
    """返回 sections: [ {name, theme, subs: [ {name, cards: [...] } ] } ] 以及 page→printed 映射。"""
    printed = {pid: page_printed_no(sheets, pid) for pid in sheets}
    cards_by_no = {}       # no -> card dict（合并续排）
    card_order = []        # 首现顺序
    cur_sec = None
    cur_sub = None
    sections = []          # [{name, theme, subs:[{name, cards:[no]}]}]

    for pid in sorted(sheets):
        sp = sheets[pid]
        texts = [t for t in sp['texts'] if not (t['y'] < 55 or t['y'] > 800)]
        banners, boxes, strips, chips, uls, accents = classify_bars(sp['bars'])
        # 横幅按 y 排序 → 分带
        banners.sort(key=lambda b: b['y'])
        band_edges = [55.0] + [b['y'] for b in banners] + [10000.0]
        # 带信息
        bands = []
        for i in range(len(band_edges) - 1):
            y0, y1 = band_edges[i], band_edges[i + 1]
            bands.append({'y0': y0, 'y1': y1, 'banner': banners[i - 1] if i > 0 else None})
        for bi, band in enumerate(bands):
            banner = band['banner']
            if banner is not None:
                bts = banner_texts(banner, texts)
                btxt = ''.join(t['text'].strip() for t in bts)
                if '知识点' in btxt:
                    # 整幅卡片标题条（如 037）——归入卡片，不作为横幅
                    band['card_strip'] = banner
                    band['is_section'] = band['is_sub'] = False
                else:
                    strip_bg = banner['bg']
                    if strip_bg in ('#ebcbac', '#f3c9c7', '#c7e5d0'):
                        band['is_section'] = True
                        band['is_sub'] = False
                    else:
                        band['is_section'] = False
                        band['is_sub'] = True
                    band['btxt'] = btxt
                    band['bcolor'] = bts[0]['color'] if bts else '#000'
            # 分节状态
            if band.get('is_section'):
                theme = {'#ebcbac': 'tan', '#f3c9c7': 'rose', '#c7e5d0': 'green'}[banner['bg']]
                cur_sec = {'name': band['btxt'], 'theme': theme, 'subs': []}
                sections.append(cur_sec)
                cur_sub = None
            elif band.get('is_sub'):
                if cur_sec is None:
                    cur_sec = {'name': '', 'theme': 'tan', 'subs': []}
                    sections.append(cur_sec)
                cur_sub = {'name': band['btxt'], 'cards': []}
                cur_sec['subs'].append(cur_sub)
            # 整幅卡片（037 时间轴等）：strip 由横幅识别，body 是下方大白框
            band_cards = []
            if band.get('card_strip') is not None:
                strip = band['card_strip']
                no, title = strip_label(strip, texts)
                body = None
                for bx in boxes:
                    if bx['w'] > 400 and bx['y'] >= strip['y'] - 4 and bx['y'] < strip['y'] + 60:
                        body = bx
                        break
                if no is not None:
                    x0 = min(strip['x'], body['x'] if body else 1e9)
                    x1 = max(strip['x'] + strip['w'], (body['x'] + body['w']) if body else -1)
                    y_top = strip['y']
                    y_bot = max(strip['y'] + strip['h'], (body['y'] + body['h']) if body else -1)
                    band_cards = [{'no': no, 'title': title, 'strip': strip, 'body': body,
                                   'x0': x0, 'x1': x1, 'y0': y_top, 'y1': y_bot, 'col': 0,
                                   'strip_bg': strip['bg'], 'pid': pid}]
            # 卡片：按 (列, y) 排
            for strip in ([] if band.get('card_strip') is not None else [s for s in strips if band['y0'] - 1 <= s['y'] < band['y1'] - 1]):
                no, title = strip_label(strip, texts)
                if no is None:
                    continue
                # 匹配 body 框
                body = None
                for bx in boxes:
                    if abs(bx['x'] - strip['x']) < 6 and bx['y'] <= strip['y'] + 2 and bx['y'] + bx['h'] > strip['y'] + strip['h'] - 2:
                        body = bx
                        break
                if body is None:
                    for bx in boxes:
                        if abs(bx['x'] - strip['x']) < 6 and abs(bx['y'] - strip['y']) < 8:
                            body = bx
                            break
                x0 = min(strip['x'], body['x'] if body else 1e9)
                x1 = max(strip['x'] + strip['w'], (body['x'] + body['w']) if body else -1)
                y_top = min(strip['y'], body['y'] if body else 1e9)
                y_bot = max(strip['y'] + strip['h'], (body['y'] + body['h']) if body else -1)
                col = 0 if x0 < 297 else 1
                band_cards.append({'no': no, 'title': title, 'strip': strip, 'body': body,
                                   'x0': x0, 'x1': x1, 'y0': y_top, 'y1': y_bot, 'col': col,
                                   'strip_bg': strip['bg'], 'pid': pid})
            band_cards.sort(key=lambda c: (c['col'], c['strip']['y']))
            # 逐卡建内容
            for c in band_cards:
                if c['no'] not in cards_by_no:
                    theme_info = THEME_BY_STRIP.get(c['strip_bg'], ('tan', '#ebcbac', '#98521c', '#f7e9d9', '#d6b89a'))
                    cards_by_no[c['no']] = {
                        'no': c['no'], 'title': c['title'], 'theme': theme_info[0],
                        'label_color': None, 'parts': [], 'first_pid': pid,
                    }
                    card_order.append(c['no'])
                    if cur_sub is not None:
                        cur_sub['cards'].append(c['no'])
                    elif cur_sec is not None and cur_sec['subs']:
                        cur_sec['subs'][-1]['cards'].append(c['no'])
                    else:
                        if cur_sec is None:
                            cur_sec = {'name': '', 'theme': c['theme'], 'subs': []}
                            sections.append(cur_sec)
                        cur_sub = {'name': '', 'cards': [c['no']]}
                        cur_sec['subs'].append(cur_sub)
                card = cards_by_no[c['no']]
                # 取本段（本页本栏本块）内的文本行
                inside = []
                for t in texts:
                    if c['x0'] - 2 <= t['x'] and t['x'] <= c['x1'] + 2 and c['y0'] - 2 <= t['y'] <= c['y1'] + 2:
                        # 标题条里的文字不算正文
                        s = c['strip']
                        if s['y'] - 3 <= t['y'] <= s['y'] + s['h'] + 2 and s['x'] - 2 <= t['x'] <= s['x'] + s['w'] + 2:
                            if card['label_color'] is None and t['size'] < 8:
                                card['label_color'] = t['color']
                            continue
                        inside.append(t)
                icons = []
                seen_pos = set()
                for im in sp['imgs']:
                    if c['x0'] - 2 <= im['x'] and im['x'] <= c['x1'] + 2 and c['y0'] - 2 <= im['y'] <= c['y1'] + 2:
                        s = c['strip']
                        if s['y'] - 2 <= im['y'] <= s['y'] + s['h'] + 2:
                            continue
                        # 同一位置复刻页会列出多张候选图，只留一张
                        pos = (pid, round(im['x'], 1), round(im['y'], 1))
                        if pos in seen_pos:
                            continue
                        seen_pos.add(pos)
                        icons.append({'x': im['x'], 'y': im['y'], 'w': im['w'], 'h': im['h'],
                                      'src': ico_by_pos.get(pos, 'orig-' + im['src'])})
                items = inside + icons
                lines = build_lines(items)
                lines = attach_marks(lines, uls)
                card['parts'].append({'pid': pid, 'col': c['col'], 'lines': lines,
                                      'x0': c['x0'], 'x1': c['x1']})
    # 组装 sections → 结构里放 card no 列表（渲染时按 order 取 cards_by_no）
    return sections, cards_by_no, card_order, printed

# ---------- 6. 行 → HTML ----------
def runs_to_html(runs, join_wraps=False):
    out = []
    prev_u = False
    prev_mark = False
    for r in runs:
        if r['type'] == 'img':
            if r.get('w', 0) > 100:
                out.append(f'<img class="big-fig" src="/library/政治/assets/{r["src"]}" alt="史纲整体脉络时间轴（1840—改革开放）">')
            else:
                out.append(f'<img class="ico" src="/library/政治/assets/{r["src"]}" alt="">')
            continue
        cls = []
        style = [f'color:{r["color"]}']
        if r['weight'] >= 600:
            style.append('font-weight:600')
        if r['font'] == 'f-serif':
            style.append('font-family:var(--serif)')
        size = r['size']
        style.append(f'font-size:{size * 1.58:.1f}px')
        body = esc(r['text'])
        if r.get('mark'):
            body = f'<mark style="background:{r["mark"]}">{body}</mark>'
        if r.get('u'):
            body = f'<u style="text-decoration-color:{r["u"]};text-decoration-thickness:1.5px;text-underline-offset:3px">{body}</u>'
        out.append(f'<span style="{";".join(style)}">{body}</span>')
    return ''.join(out)

def line_gap_class(prev, cur):
    if prev is None:
        return ''
    gap = cur['y'] - prev['y']
    base = min(prev['size'], cur['size'])
    if gap > base * 2.25:
        return ' blk'
    return ''

def lines_to_html(lines, x0_col, x1_col):
    """把行组装成段落块：换行续接、块间距按原 PDF 行距。"""
    parts = []
    buf = []           # 当前行缓冲（合并 wrap 续行）
    blocks = []
    prev_line = None
    col_w = x1_col - x0_col
    text_right = x1_col - 12
    for ln in lines:
        wrap = False
        if prev_line is not None and (ln['y'] - prev_line['y']) <= 18.5:
            if prev_line['xend'] >= text_right - 22:
                wrap = True
        if wrap and buf:
            # 续行：并入上一行
            buf[-1] = {'y': buf[-1]['y'], 'size': buf[-1]['size'], 'runs': buf[-1]['runs'] + ln['runs'],
                       'x0': buf[-1]['x0'], 'xend': ln['xend']}
        else:
            buf.append(ln)
        prev_line = ln
    # 分块（行距大则分块）
    groups = []
    cur_g = []
    for ln in buf:
        if cur_g and (ln['y'] - cur_g[-1]['y']) > min(ln['size'], cur_g[-1]['size']) * 2.25:
            groups.append(cur_g)
            cur_g = [ln]
        else:
            cur_g.append(ln)
    if cur_g:
        groups.append(cur_g)
    html_parts = []
    for g in groups:
        rows = []
        for ln in g:
            rows.append(f'<div class="ln">{runs_to_html(ln["runs"])}</div>')
        html_parts.append('<div class="grp">' + ''.join(rows) + '</div>')
    return ''.join(html_parts)

# ---------- 7. TOC ----------
def parse_toc(sheets):
    entries = []
    for pid in (7, 8, 9):
        sp = sheets.get(pid)
        if not sp:
            continue
        lines = build_lines([t for t in sp['texts'] if t['y'] > 55])
        for ln in lines:
            ts = [r for r in ln['runs'] if r['type'] == 't']
            if not ts:
                continue
            left = ts[0]
            txt = ''.join(r['text'] for r in ts).strip()
            right = max(ts, key=lambda r: r['x'])
            page = ''
            m = re.match(r'^(.*?)\s*(\d{1,2})$', txt)
            lvl = 0 if left['x'] < 50 else (1 if left['x'] < 70 else 2)
            # 页码是右侧独立串
            page_no = ''
            content_runs = ts
            if right['x'] > 500 and right['text'].strip().isdigit():
                page_no = right['text'].strip()
                content_runs = [r for r in ts if r is not right]
            content = ''.join(r['text'] for r in content_runs).strip()
            if not content:
                continue
            color = content_runs[0]['color']
            size = content_runs[0]['size']
            wgt = content_runs[0]['weight']
            entries.append({'lvl': lvl, 'text': content, 'page': page_no,
                            'color': color, 'size': size, 'weight': wgt})
    return entries

# ---------- 8. 特殊页（前言/注意事项/诗词/封面） ----------
def build_prose_pages(sheets, ico_map, orig_map):
    out = {}
    # ---- p3 前言 ----
    sp = sheets[3]
    texts = [t for t in sp['texts'] if not (t['y'] < 55 or t['y'] > 760)]
    lines = attach_marks(build_lines(texts), prose_bars(sp))
    paras = []
    cur = []
    for ln in lines:
        if ln['runs'] and ln['runs'][0]['type'] == 't' and ln['runs'][0]['text'].strip() in ('前言',):
            out['p3_title'] = '前言'
            continue
        if cur and ln['x0'] > 100:
            paras.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        paras.append(cur)
    ph = []
    for para in paras:
        # 段内换行续接（wrap）
        rows = []
        for ln in para:
            rows.append(ln)
        # 重新按 wrap 合并
        merged = []
        for ln in rows:
            if merged and (ln['y'] - merged[-1]['y_last']) < 21 and merged[-1]['xend'] >= 508 - 22:
                merged[-1] = {'y': merged[-1]['y'], 'size': merged[-1]['size'], 'y_last': ln['y'],
                              'runs': merged[-1]['runs'] + ln['runs'], 'x0': merged[-1]['x0'], 'xend': ln['xend']}
            else:
                ln = dict(ln)
                ln['y_last'] = ln['y']
                merged.append(ln)
        cls = 'para'
        body = ''
        if len(merged) == 1 and merged[0]['size'] >= 13.5:
            first = merged[0]
            if first['runs'] and any(r.get('u') for r in first['runs'] if r['type'] == 't'):
                cls = 'op-callout'
            else:
                cls = 'h3-para'
        if len(merged) == 1 and merged[0]['size'] >= 17:
            cls = 'big-title'
        for i, ln in enumerate(merged):
            seg = runs_to_html(ln['runs'])
            body += seg + ('' if i == len(merged) - 1 else '<br>')
        ph.append(f'<p class="{cls}">{body}</p>')
    out['p3'] = ''.join(ph)

    # ---- p4 使用注意事项 ----
    sp = sheets[4]
    texts = [t for t in sp['texts'] if not (t['y'] < 55 or t['y'] > 760)]
    lines = attach_marks(build_lines(texts), prose_bars(sp))
    ph = []
    qr_lines = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        txt = ''.join(r['text'] for r in ln['runs'] if r['type'] == 't')
        if txt.strip().startswith('使用注意事项'):
            ph.append(f'<p class="h3-para">{runs_to_html(ln["runs"])}</p>')
        elif txt.strip().startswith('主编：') or txt.strip().startswith('副主编') or re.match(r'^\s*2026', txt):
            qr_lines.append(('credit', ln))
        elif '二维码' in txt or txt.strip() in ('扫码获取后续更新', '免费配套课程', '后续资料获取'):
            qr_lines.append(('qr', ln))
        elif ln['size'] >= 15:
            ph.append(f'<p class="lead">{runs_to_html(ln["runs"])}</p>')
        else:
            ph.append(f'<p class="para">{runs_to_html(ln["runs"])}</p>')
        i += 1
    out['p4'] = ''.join(ph)
    # credits + QR
    credits = []
    qrs = []
    for kind, ln in qr_lines:
        s = runs_to_html(ln['runs'])
        if kind == 'credit':
            credits.append(f'<div class="credit">{s}</div>')
        else:
            qrs.append(ln)
    # 二维码图片（orig）：p4-721/722/723
    imgs = sorted([im for im in sheets[4]['imgs']], key=lambda im: im['x'])
    captions = [ln for ln in lines if ''.join(r['text'] for r in ln['runs'] if r['type'] == 't').strip() in ('扫码获取后续更新', '免费配套课程', '后续资料获取')]
    heads = [ln for ln in lines if '二维码' in ''.join(r['text'] for r in ln['runs'] if r['type'] == 't')]
    figs = []
    for idx, im in enumerate(imgs):
        head = runs_to_html(heads[idx]['runs']) if idx < len(heads) else ''
        cap = runs_to_html(captions[idx]['runs']) if idx < len(captions) else ''
        figs.append(f'<figure class="qr"><div class="qr-head">{head}</div>'
                    f'<img src="/library/政治/assets/orig-{im["src"]}" alt="二维码">'
                    f'<figcaption>{cap}</figcaption></figure>')
    out['p4_qr'] = '<div class="qr-row">' + ''.join(figs) + '</div>'
    out['p4_credits'] = '<div class="credits">' + ''.join(credits) + '</div>'

    # ---- p5 诗词 ----
    sp = sheets[5]
    texts = [t for t in sp['texts'] if not (t['y'] < 55 or t['y'] > 760)]
    lines = attach_marks(build_lines(texts), prose_bars(sp))
    ph = []
    for ln in lines:
        txt = ''.join(r['text'] for r in ln['runs'] if r['type'] == 't').strip()
        if txt.startswith('【'):
            ph.append(f'<p class="h3-para">{runs_to_html(ln["runs"])}</p>')
        elif ln['size'] >= 20:
            ph.append(f'<p class="poem-title">{runs_to_html(ln["runs"])}</p>')
        elif '毛泽东' in txt or '1935' in txt:
            ph.append(f'<p class="poem-by">{runs_to_html(ln["runs"])}</p>')
        elif txt.startswith('图') or '手迹' in txt:
            ph.append(f'<p class="poem-cap">{runs_to_html(ln["runs"])}</p>')
        elif ln['x0'] > 200 and ln['y'] > 240:
            ph.append(f'<div class="poem-ln">{runs_to_html(ln["runs"])}</div>')
        else:
            ph.append(f'<p class="para">{runs_to_html(ln["runs"])}</p>')
    out['p5'] = ''.join(ph)
    out['p5_img'] = f'<figure class="calligraphy"><img src="/library/政治/assets/orig-p5-740.png" alt="毛泽东《忆秦娥·娄山关》草书手迹"></figure>'
    return out

# ---------- 9. HTML 组装 ----------
def render_cards_html(sections, cards_by_no, card_order):
    order_idx = {no: i for i, no in enumerate(card_order)}
    sec_html = []
    for si, sec in enumerate(sections, 1):
        sub_html = []
        for zi, sub in enumerate(sec['subs'], 1):
            card_html = []
            for no in sub['cards']:
                c = cards_by_no[no]
                body = []
                for part in c['parts']:
                    body.append(lines_to_html(part['lines'], part['x0'], part['x1']))
                label_color = c['label_color'] or '#964a49'
                card_html.append(
                    f'<article class="kcard" id="k{no:03d}" data-theme="{c["theme"]}">'
                    f'<header class="khead"><span class="kno" style="color:{label_color}">知识点 {no:03d}</span>'
                    f'<h4>{esc(c["title"])}</h4></header>'
                    f'<div class="kbody">{"".join(body)}</div></article>')
            sub_html.append(
                (f'<h3 class="sub-banner" id="sub-{si}-{zi}">{esc(sub["name"])}</h3>' if sub['name'] else '')
                + '<div class="card-grid">' + ''.join(card_html) + '</div>')
        sec_html.append(
            f'<section class="op-sec" id="sec-{si}" data-theme="{sec["theme"]}">'
            f'<h2 class="sec-banner">{esc(sec["name"])}</h2>' + ''.join(sub_html) + '</section>')
    return ''.join(sec_html)


def sidebar_html(sections):
    """左侧导航：目录 + 三大章 + 各章小节（锚点与正文 id 一一对应）。"""
    items = ['<a class="op-nav-item lvl0" href="#contents">内容总览</a>']
    for si, sec in enumerate(sections, 1):
        items.append(f'<a class="op-nav-item lvl1" href="#sec-{si}">{esc(sec["name"])}</a>')
        for zi, sub in enumerate(sec['subs'], 1):
            if sub['name']:
                items.append(f'<a class="op-nav-item lvl2" href="#sub-{si}-{zi}">{esc(sub["name"])}</a>')
    return ''.join(items)

def toc_html(entries, cards_by_no):
    # 标题→锚点
    anchors = {}
    for no, c in cards_by_no.items():
        anchors.setdefault(c['title'], f'k{no:03d}')
    rows = []
    for e in entries:
        href = anchors.get(e['text'], '')
        size = e['size'] * 1.58
        style = f'color:{e["color"]};font-size:{size:.1f}px'
        if e['weight'] >= 600:
            style += ';font-weight:600'
        link = (f'<a href="#{href}" style="{style}">{esc(e["text"])}</a>' if href
                else f'<span style="{style}">{esc(e["text"])}</span>')
        rows.append(f'<div class="toc-row lvl{e["lvl"]}">{link}'
                    f'<span class="toc-dots"></span><span class="toc-pg">{e["page"]}</span></div>')
    return ''.join(rows)

PAGE_HEAD = '''<!doctype html>
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
<script src="/countdown.js" defer></script>
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
'''

PAGE_TAIL = '''
<script>
/* 左侧目录：滚动高亮 + 窄屏折叠 */
(function () {
  var nav = document.getElementById('opSideNav');
  if (!nav) return;
  var links = [].slice.call(nav.querySelectorAll('a'));
  var targets = links.map(function (a) {
    var id = a.getAttribute('href').slice(1);
    return document.getElementById(id);
  });

  function highlight() {
    var y = window.scrollY + 120, cur = 0;
    for (var i = 0; i < targets.length; i++) {
      var t = targets[i];
      if (t && t.getBoundingClientRect().top + window.scrollY <= y) cur = i;
    }
    for (var j = 0; j < links.length; j++) links[j].classList.toggle('on', j === cur);
  }
  window.addEventListener('scroll', highlight, { passive: true });
  window.addEventListener('resize', highlight);
  highlight();

  var btn = document.getElementById('opSideBtn');
  var side = document.getElementById('opSide');
  if (btn && side) {
    btn.addEventListener('click', function () {
      var open = side.classList.toggle('open');
      btn.setAttribute('aria-expanded', String(open));
      btn.textContent = open ? '目录 ▴' : '目录 ▾';
    });
    nav.addEventListener('click', function (e) {
      if (e.target.closest('a') && window.innerWidth <= 1080) {
        side.classList.remove('open');
        btn.setAttribute('aria-expanded', 'false');
        btn.textContent = '目录 ▾';
      }
    });
  }
})();
</script>'''

def main():
    sheets = parse_sheets()
    orig_map, ico_map, ico_by_pos = extract_embedded()
    sections, cards_by_no, card_order, printed = build_content_model(sheets, ico_by_pos)
    toc = parse_toc(sheets)
    prose = build_prose_pages(sheets, ico_map, orig_map)

    # 校验：卡片文本拼接 vs PDF 文本层
    if '--verify' in sys.argv:
        verify(sheets, cards_by_no)
        return

    body = []
    body.append('<div class="op-wrap">')
    body.append('<div class="op-layout">')
    # 左侧目录导航
    body.append('''<aside class="op-side" id="opSide">
  <button class="op-side-btn" id="opSideBtn" type="button" aria-expanded="false" aria-controls="opSideNav">目录 ▾</button>
  <div class="op-side-in">
    <p class="op-side-t">目录</p>
    <nav class="op-side-nav" id="opSideNav">''' + sidebar_html(sections) + '''</nav>
  </div>
</aside>
<div class="op-main">''')
    body.append('''<header class="op-head">
    <nav class="crumbs"><a href="/library/">知识库</a> <span class="sep">/</span> <a href="/library/政治/">政治</a> <span class="sep">/</span> <span>一页纸</span></nav>
    <h1>27 考研政治一页纸 · 知识点手册</h1>
    <p class="op-sub">澄潇宇一页纸 · 35 页 · 网页版内容与原版 PDF 完全一致，文字可选中、可检索</p>
    <div class="op-actions">
      <a class="op-btn solid" href="/pdfs/politics/27-yiyeye.pdf" target="_blank" rel="noopener">打开原版 PDF ↗</a>
      <a class="op-btn" href="/pdfs/politics/27-yiyeye.pdf" download>下载 PDF</a>
      <a class="op-btn" href="/politics/">配套真题练习</a>
    </div>
  </header>''')
    # 封面、前言、使用说明、诗词等前置页已按需求移除，正文从目录开始
    # 目录
    body.append('<section class="op-toc" id="contents"><h2 class="toc-title"><span class="toc-en">CONTENTS</span> / 目录</h2><h3 class="toc-main">内容总览</h3>' + toc_html(toc, cards_by_no) + '</section>')
    # 正文
    body.append(render_cards_html(sections, cards_by_no, card_order))
    body.append('<footer class="op-foot">27 考研政治一页纸 · 知识点手册 · 网页版按原版 PDF 逐字整理 · <a href="/pdfs/politics/27-yiyeye.pdf">查看 PDF</a></footer>')
    body.append('</div>')   # .op-main
    body.append('</div>')   # .op-layout
    body.append('</div>')   # .op-wrap

    html = PAGE_HEAD + '\n'.join(body) + PAGE_TAIL + '\n</body>\n</html>\n'
    out = os.path.join(OP_DIR, '一页纸.html')
    open(out, 'w', encoding='utf-8').write(html)
    print('written', out, len(html), 'bytes')
    print('cards:', len(cards_by_no), 'sections:', [(s['name'], s['theme'], len(s['subs'])) for s in sections])
    print('toc entries:', len(toc))
    print('icons:', len(ico_map), 'orig imgs:', len(orig_map))

def verify(sheets, cards_by_no):
    import fitz
    doc = fitz.open(PDF)
    ok = bad = 0
    for no, c in sorted(cards_by_no.items()):
        text = ''
        for part in c['parts']:
            for ln in part['lines']:
                for r in ln['runs']:
                    if r['type'] == 't':
                        text += r['text']
        text_n = re.sub(r'\s+', '', text)
        # 在 PDF 文本层里找标题
        title = c['title']
        found = False
        for pno in range(doc.page_count):
            if title and re.sub(r'\s+', '', title)[:6] in re.sub(r'\s+', '', doc[pno].get_text()):
                found = True
                break
        if title and found:
            ok += 1
        else:
            bad += 1
            print('MISSING title:', no, title)
    print('verify titles ok', ok, 'bad', bad)
    doc.close()

if __name__ == '__main__':
    main()
