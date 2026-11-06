"""从解析 PDF 提取写作范文（整页 OCR 版，兼容无文本层的扫描件）。

流程：
  1) 逐页 300dpi 渲染 → tesseract --psm 4 tsv → 行级 bbox + 文本（结果缓存）
  2) 找写作章节（Section III / Writing）
  3) 以「范文首句」定位起点（Notice / Dear / In the picture ...），同栏向下连续收集英文行
  4) 清洗：去圈码、去中文乱码行、合并断行

用法:
  python3 build-essays.py y1-2020            # 单套调试
  python3 build-essays.py --all [out.json]   # 批量
"""
import pymupdf, re, sys, json, pathlib, subprocess, tempfile, os, csv

PDF_DIR = pathlib.Path('/Users/feikntn111/File_no_iCloud/kaoyan-website/kaoyan-hub/exam/pdf')
CACHE = pathlib.Path('/tmp/ocr-cache')
CACHE.mkdir(exist_ok=True)
DPI = 300
STOP = {'the','a','an','of','to','and','in','is','are','that','with','for','on','as','it','be','this',
        'we','you','our','will','can','not','but','by','their','from','at','have','has','was','were',
        'which','they','your','if','there','more','than','also','its','should','would','may','all','one',
        'who','what','when','do','does','these','those','them','he','she','his','her','i','my','me','so',
        'been','being','could','into','about','how','many','much','some','other','such'}
WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]+")
TEMPLATE = re.compile(r'_{2,}|--{2,}|…{2,}')
DIRECTION = re.compile(r'Write your answer|ANSWER SHEET|in about 1|Write an essay|Directions|'
                       r'Do not use your own name|You should write|\(\s*\d+\s*points', re.I)

START_KEYS = ('notice', 'dear', 'towhom', 'iamwriting', 'i’mwriting', 'iamglad', 'i’mglad',
              'wouldliketo', 'asisshown', 'asisvividly', 'asisdepicted', 'asillustrated',
              'intheleftpicture', 'inthepicture', 'inthecartoon', 'inthedrawing', 'inthephoto',
              'thepicturedepicts', 'thepictureshows', 'thepictureabove', 'thepicturebelow',
              'thepicturepresents', 'thepicturereveals', 'thepictureillustrates',
              'thispicture', 'thiscartoon', 'itisdepicted', 'itisillustrated', 'itisshown',
              'recently', 'nowadays', 'withthedevelopment', 'whenitcomesto', 'thereis', 'thereare',
              'manypeople', 'thetwopictures', 'twomen', 'fromthepicture', 'simpleasit')


def squash(t):
    return re.sub(r'\s+', '', t.lower())


def is_start(t):
    sq = squash(t)[:40]
    return any(sq.startswith(k) or (len(sq) > 6 and k in sq[:24]) for k in START_KEYS)


def eng_words(t):
    return WORD.findall(t)


def is_eng(t):
    ws = eng_words(t)
    if len(ws) < 4:
        return False
    low = [w.lower() for w in ws]
    stop = sum(1 for w in low if w in STOP)
    need = 2 if len(low) < 10 else 3
    if stop < need:
        return False
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 12:
        return False
    if sum(1 for w in low if len(w) > 2) < 3:
        return False
    lowr = sum(1 for c in t if c.islower())
    return lowr / max(1, len(letters)) >= 0.42


def ocr_lines(pdf, pno):
    """整页 OCR，返回 [[x0,y0,x1,y1,text], ...]（PDF 坐标）"""
    key = CACHE / f'{pathlib.Path(pdf).stem}-{pno}.json'
    if key.exists():
        return json.loads(key.read_text())
    doc = pymupdf.open(pdf)
    pg = doc[pno]
    tmp = tempfile.mkdtemp()
    png = os.path.join(tmp, 'p.png')
    pg.get_pixmap(dpi=DPI).save(png)
    base = os.path.join(tmp, 'o')
    subprocess.run(['tesseract', png, base, '-l', 'eng', '--psm', '4', 'tsv'],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = list(csv.DictReader(open(base + '.tsv', encoding='utf-8'),
                               delimiter='\t', quoting=csv.QUOTE_NONE))
    sc = DPI / 72.0
    groups = {}
    for r in rows:
        if r.get('level') != '5':
            continue
        t = (r.get('text') or '').strip()
        if not t:
            continue
        k = (r['block_num'], r['par_num'], r['line_num'])
        x0 = int(r['left']); y0 = int(r['top'])
        x1 = x0 + int(r['width']); y1 = y0 + int(r['height'])
        g = groups.setdefault(k, {'x0': 1e9, 'y0': 1e9, 'x1': 0, 'y1': 0, 'w': []})
        g['x0'] = min(g['x0'], x0); g['y0'] = min(g['y0'], y0)
        g['x1'] = max(g['x1'], x1); g['y1'] = max(g['y1'], y1)
        g['w'].append(t)
    out = []
    for g in groups.values():
        out.append([round(g['x0'] / sc, 1), round(g['y0'] / sc, 1),
                    round(g['x1'] / sc, 1), round(g['y1'] / sc, 1), ' '.join(g['w'])])
    out.sort(key=lambda r: (r[1], r[0]))
    key.write_text(json.dumps(out, ensure_ascii=False))
    return out


def writing_pages(pdf, doc):
    n = doc.page_count
    for i in range(n - 1, int(n * 0.25), -1):
        for row in ocr_lines(pdf, i):
            sq = squash(row[4])
            if 'sectioniii' in sq[:30] or sq[:22].startswith('writing') or sq[:20].startswith('section3'):
                return i
    return int(n * 0.7)


def clean_text(lines):
    out = []
    for s in lines:
        s = re.sub(r'\s+', ' ', s.strip())
        s = re.sub(r'^[\s®©@•◉◯()\[\]{}|~\-—_·•\.，,、:：;；\'"“”‘’]+', '', s)
        s = re.sub(r'^\(\s*\d\s*\)\s*|^[①-⑳]\s*', '', s)
        s = re.sub(r'[\s~\-—_|·•]+$', '', s)
        if len(s) < 8:
            continue
        letters = [c for c in s if c.isalpha()]
        if not letters:
            continue
        vow = sum(1 for c in letters if c.lower() in 'aeiouy')
        if vow / len(letters) < 0.3:
            continue
        if not is_eng(s):
            continue
        out.append(s)
    return out


def join(lines):
    out = ''
    for s in lines:
        if not out:
            out = s
        elif out.endswith('-') and s[:1].islower():
            out = out[:-1] + s
        elif re.match(r'^[a-z,;.\)]', s):
            out = out + ' ' + s
        else:
            out = out + '\n' + s
    return out


def trim_echoes(text):
    lines = text.split('\n')
    pref = [' '.join(l.split()[:2]).lower() for l in lines]
    for i in range(len(lines)):
        if pref[i] and pref.count(pref[i]) >= 3:
            return '\n'.join(lines[:i]).rstrip()
    return text


def collect(pdf, doc, pi, col, y_from):
    pg = doc[pi]
    W = pg.rect.width
    rows = [r for r in ocr_lines(pdf, pi) if (r[0] < W * 0.42) == (col == 0) and r[1] >= y_from - 6]
    rows.sort(key=lambda r: r[1])
    acc, last = [], y_from
    for r in rows:
        t = r[4]
        if not is_eng(t) or TEMPLATE.search(t) or DIRECTION.search(t):
            break
        if acc and r[1] - last > 40:
            break
        acc.append((pi, r))
        last = r[3]
    return acc


def find_runs(pdf, doc, start):
    out = {'A': [], 'B': []}
    part = 'A'
    for pi in range(start, doc.page_count):
        W = doc[pi].rect.width
        for r in ocr_lines(pdf, pi):
            t = r[4]
            m = re.match(r'^(Part\s*([AB]))\b', t.strip(), re.I)
            if m and len(t) < 40:
                part = m.group(2).upper()
                continue
            if not is_start(t) or not is_eng(t):
                continue
            col = 0 if r[0] < W * 0.42 else 1
            run = collect(pdf, doc, pi, col, r[1])
            cur = pi
            for _ in range(2):
                npi = cur + 1
                if npi >= doc.page_count:
                    break
                tail = collect(pdf, doc, npi, col, 0)
                if tail and tail[0][1][1] < doc[npi].rect.height * 0.45:
                    run += tail
                    cur = npi
                else:
                    break
            words = sum(len(eng_words(rr[4])) for _, rr in run)
            if words >= 50:
                out[part].append((pi, col, run, words))
    return out


def run_one(pid, verbose=False):
    pdf = PDF_DIR / f'{pid}-sol.pdf'
    doc = pymupdf.open(pdf)
    start = writing_pages(pdf, doc)
    runs = find_runs(pdf, doc, start)
    res = {}
    for k in ('A', 'B'):
        cands = runs[k]
        if not cands:
            res[k] = None
            continue
        cands.sort(key=lambda c: -c[3])
        pi, col, run, words = cands[0]
        text = join(clean_text([rr[4] for _, rr in run]))
        text = trim_echoes(text)
        res[k] = {'page': pi + 1, 'words': words, 'text': text}
        if verbose:
            print(f'--- Part {k}  p{pi+1} words={words}')
            print(text)
    return res


if __name__ == '__main__':
    if sys.argv[1] == '--all':
        out = {}
        for pdf in sorted(PDF_DIR.glob('*-sol.pdf')):
            pid = pdf.stem.replace('-sol', '')
            try:
                r = run_one(pid)
            except Exception as e:
                print(pid, 'ERR', e, flush=True)
                continue
            out[pid] = r
            print(pid, {k: (v['words'] if v else None) for k, v in r.items()}, flush=True)
        path = sys.argv[2] if len(sys.argv) > 2 else '/tmp/essays-draft.json'
        json.dump(out, open(path, 'w'), ensure_ascii=False, indent=1)
        print('saved', path)
    else:
        run_one(sys.argv[1], verbose=True)
