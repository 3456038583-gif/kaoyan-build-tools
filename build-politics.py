#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""考研政治真题解析：从原卷 PDF 提取题干 / 选项 / 答案，输出 politics/data/*.js

用法：
  python3 build-politics.py            # 全部年份，写数据文件
  python3 build-politics.py --probe    # 只打印解析结果，不写文件
  python3 build-politics.py 2010 2015  # 只处理指定年份
"""
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import pymupdf

SRC = Path('/Users/feikntn111/Desktop/考研政治资料/考研政治真题')
SITE = Path.home() / 'File_no_iCloud/kaoyan-website/kaoyan-hub'
OUT = SITE / 'politics/data'

# 各年原卷 / 解析文件
PAPERS = {
    2010: ('2010年政治真题/2010年考研政治真题.pdf', '2010年政治真题/2010年考研政治答案解析.pdf'),
    2011: ('2011年政治真题/2011年考研政治真题.pdf', '2011年政治真题/2011年考研政治答案解析.pdf'),
    2012: ('2012年政治真题/2012年考研政治真题.pdf', '2012年政治真题/2012年考研政治答案解析.pdf'),
    2013: ('2013年政治真题/2013年考研政治真题.pdf', '2013年政治真题/2013年考研政治答案解析.pdf'),
    2014: ('2014年政治真题/2014年考研政治真题.pdf', '2014年政治真题/2014年考研政治答案解析.pdf'),
    2015: ('2015年政治真题/2015年考研政治真题.pdf', '2015年政治真题/2015年考研政治答案解析.pdf'),
    2016: ('2016年政治真题/2016年考研政治真题.pdf', '2016年政治真题/2016年考研政治答案解析.pdf'),
    2017: ('2017年政治真题/2017年考研政治真题.pdf', '2017年政治真题/2017年考研政治答案解析.pdf'),
    2018: ('2018年政治真题/2018年考研政治真题.pdf', '2018年政治真题/2018年考研政治答案解析.pdf'),
    2019: ('2019年政治真题/2019年考研政治真题.pdf', '2019年政治真题/2019年考研政治答案解析.pdf'),
    2020: ('2020年政治真题/2020年考研政治真题.pdf', '2020年政治真题/2020年考研政治答案解析.pdf'),
    2021: ('2021年政治真题/2021年考研政治真题（拆分版）.pdf', '2021年政治真题/2021年考研政治答案解析.pdf'),
    2022: ('2022年政治真题/2022年考研政治真题.pdf', '2022年政治真题/2022年考研政治真题答案及解析.pdf'),
    2023: ('2023年政治真题/2023年考研政治真题.pdf', '2023年政治真题/2023年考研政治真题答案及解析.pdf'),
    2024: ('2024年政治真题/2024年考研政治真题及答案.pdf', '2024年政治真题/2024年考研政治真题及答案.pdf'),
    2025: ('2025年政治真题/2025年考研政治真题及答案.pdf', '2025年政治真题/2025年考研政治真题及答案.pdf'),
    2026: ('2026年政治真题/2026考研政治真题及答案（苏一版）.pdf', '2026年政治真题/2026考研政治真题及答案（苏一版）.pdf'),
}

# 常见 OCR 错字（原卷文字层/OCR 的固定混淆）
FIXES = [
    ('单顶', '单选'), ('选顶', '选项'), ('符台', '符合'), ('技木', '技术'), ('艺木', '艺术'),
    ('关千', '关于'), ('在千', '在于'), ('鉴千', '鉴于'), ('由千', '由于'), ('处千', '处于'),
    ('属千', '属于'), ('基千', '基于'), ('对千', '对于'), ('等千', '等于'), ('至千', '至于'),
    ('位千', '位于'), ('区别千', '区别于'), ('起千', '起于'), ('巳经', '已经'), ('己经', '已经'),
    ('未来', '未来'), ('共嬴', '共赢'), ('双嬴', '双赢'), ('全国人民代表大会', '全国人民代表大会'),
    ('莲勃', '蓬勃'), ('实线', '实践'), ('马马思', '马克思'),
    # ── OCR 把题号认成汉字时留下的残字（「书2010年」= 6.2010年）──
    ('书2010年', '2010年'), ('托2003年', '2003年'), ('午2011年', '2011年'),
    ('乓与“天宫一号', '与“天宫一号'), ('乓2012年', '2012年'), ('拉2012年', '2012年'),
    ('拉2017年', '2017年'), ('拉胡锦涛总书记', '胡锦涛总书记'),
    ('妞社会主义法治理念', '社会主义法治理念'), ('丑“和为贵”', '“和为贵”'),
    ('迈党的十八大', '党的十八大'), ('茹PM2.5', 'PM2.5'), ('菇“可上九天揽月', '“可上九天揽月'),
    ('础柏拉图说', '柏拉图说'), ('碑个人品德', '个人品德'), ('托.近年来', '近年来'),
    ('托2013年', '2013年'), ('托J第二次世界大战后', '第二次世界大战后'),
    ('第盆f社会主义', '社会主义'), ('笫廷党群关系', '党群关系'), ('笫共2014年', '2014年'),
    ('第廷2015年', '2015年'), ('笫虴严肃党内政治生活', '严肃党内政治生活'),
    ('第廷中国人民解放军', '中国人民解放军'), ('第钰2018年', '2018年'),
    ('24“十三五”时期', '“十三五”时期'), ('安是中國革命的圣地', '延安是中国革命的圣地'),
    ('安是中国革命的圣地', '延安是中国革命的圣地'), ('1013年9月7日', '2013年9月7日'),
    ('18 94年1月3日', '1894年1月3日'),
    # ── 常见 OCR 错字 ──
    ('取决千', '取决于'), ('用千', '用于'), ('深人', '深入'), ('人侵', '入侵'),
    ('井且', '并且'), ('井没有', '并没有'), ('井发表', '并发表'), ('井不意味', '并不意味'),
    ('淡话', '谈话'), ('准海', '淮海'), ('平律', '平津'), ('煤发', '爆发'),
    ('为积', '为枳'), ('延延安', '延安'), ('杜会主义', '社会主义'), ('彰湖列岛', '澎湖列岛'), ('安整风运动', '延安整风运动'), ('二一头牵着', '一头牵着'), ('状点', '状态'), ('弓领', '引领'), ('般实', '殷实'),
    # ── 扫描卷高频错字（笫/井/苺 这类形近字整卷都有）──
    ('双抱菇', '双孢菇'), ('秸秤', '秸秆'), ('地苺', '地莓'), ('忏然', '怦然'), ('禁铜', '禁锢'),
    ('嬴家', '赢家'), ('金触', '金融'), ('进人', '进入'), ('人侵', '入侵'),
    ('(S分)', '(5分)'), ('（S分）', '（5分）'), ('(S 分)', '(5分)'),
    # OCR 吞字：2023 多选 16 选项 A「勾连挑（衅），企图…」
    ('勾连挑,', '勾连挑衅,'), ('勾连挑，', '勾连挑衅，'), ('勾连挑畔', '勾连挑衅'),
    # 源 PDF 文本层自带的错字（原卷/解析册印错或扫描认错）
    ('二噫英', '二噁英'), ('华路蓝缕', '筚路蓝缕'), ('18.7名万', '18.7万名'),
    ('2009年月起', '2009年5月起'), ('盆f社会主义市场经济体制', '社会主义市场经济体制'),
    ('钰2018年', '2018年'), ('锅碗秝盆', '锅碗瓢盆'), ('一—~', '—'),
]

# 「井」绝大多数是「并」被 OCR 认错；以下词里的「井」是真字，先保护起来
JING_WORDS = ['井冈山', '凿井', '水井', '矿井', '油井', '天井', '市井', '井水', '井盖', '井田', '井喷']
JING_RE = re.compile('|'.join(JING_WORDS))

FOOTER_PAT = re.compile(
    r'(思想政治理论试题|考研政治|绝密|考生注意事项|科目代码\s*[:：]?\s*101|'
    r'第\s*\d{1,2}\s*页|共\s*\d{1,2}\s*页|^\d{1,3}$|^\s*$|'
    r'年全国硕士研究生|全国硕士研究生招生考试$|思想政治理论$|^\s*政治\s*$|'
    r'^\s*试题\s*$|答题卡|试题册)'
)

SEC_PAT = re.compile(r'^\s*[-—一二三四１-４]\s*[、.．]')
Q_LOOSE = re.compile(r'^\s*(\d{1,3})\s*[.．、:：]')
AFTER_NUM = r'(?!\s*\d(?!\d{1,4}\s*年))'   # 排除 25. 5% 这种小数，但放行 10.1840年 / 33:2022年 / 28.80年前
Q_PAT = re.compile(r'^\s*(\d{1,3})\s*[.．、:：]' + AFTER_NUM)
OPT_PAT = re.compile(r'^\s*([A-Da-d])\s*[.．、:：]\s*(?=\S)')
ANS_PAT = re.compile(r'[\[【（(]\s*(?:标准)?答案\s*[\]】）)]')


def norm(s: str) -> str:
    s = unicodedata.normalize('NFKC', s)
    s = s.replace('\u00a0', ' ')
    # 去掉汉字/全角标点两侧的空格
    s = re.sub(r'(?<=[\u4e00-\u9fff\u3000-\u303f])\s+(?=[\u4e00-\u9fff\u3000-\u303f])', '', s)
    s = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[0-9A-Za-z])', '', s)
    s = re.sub(r'(?<=[0-9A-Za-z])\s+(?=[\u4e00-\u9fff])', '', s)
    s = re.sub(r'\s{2,}', ' ', s)
    return s.strip()


# 「千」被误认成「于」的上下文：利于 / 胜于 / 高于 / 震惊于 / 立于 / 源于 / 于是 …
QIAN_YU = re.compile(
    r'(?<=[利胜高低大多少惊别立源注动格议实基由对在至处属等位起区鉴难易限长短早晚先后强弱重轻忙急])千')
QIAN_YU2 = re.compile(r'(^|[。，,；;、])\s*千(?=是)')

# 页眉页脚「第 X 页」被行合并后，只剩一个「第」插进句子中间（改第革试验区 / 有害第物质）
STRAY_DI = re.compile(r'第(?!\s*[一二三四五六七八九十百千万亿零两〇几0-9０-９（(])')
# 多余的波浪号（保留 5~10 米 这种数值区间）
TILDE = re.compile(r'(?<=[\u4e00-\u9fff，。、；：])~(?![0-9])')


def fix_jing(s):
    """「井」→「并」，但井冈山/凿井 这类真字保留"""
    if '井' not in s:
        return s
    saved = []

    def keep(m):
        saved.append(m.group(0))
        return '\x00%d\x00' % (len(saved) - 1)

    s = JING_RE.sub(keep, s)
    s = s.replace('井', '并')
    return re.sub('\x00(\\d+)\x00', lambda m: saved[int(m.group(1))], s)


def fix_text(s: str) -> str:
    for a, b in FIXES:
        s = s.replace(a, b)
    s = s.replace('笫', '第')
    s = fix_jing(s)
    s = QIAN_YU.sub('于', s)
    s = QIAN_YU2.sub(lambda m: m.group(1) + '于', s)
    s = re.sub(r'\bS[.．](?=\d{4}年)', '', s)
    s = re.sub(r'(?<!延)安整风运动', '延安整风运动', s)
    s = re.sub(r'(?<!延)安是中国革命的圣地', '延安是中国革命的圣地', s)
    s = DEC_SPLIT.sub(r'\1.\2', s)
    s = re.sub(r'(?<=[\u4e00-\u9fff])H(?=报)', '日', s)
    s = re.sub(r'(?<=[一二三四五六七八九])[O0](?=年)', '〇', s)
    s = s.replace('[美J', '[美]').replace('[英J', '[英]').replace('[德J', '[德]')
    # 页脚「第」插进正文 + 杂符
    s = STRAY_DI.sub('', s)
    s = TILDE.sub('', s)
    s = s.replace('勹', '')
    # 单引号统一成中文弯引号
    s = s.replace('`', '‘').replace("'", '’')
    s = re.sub(r'(\d(?:\.\d+)?)名万', r'\1万名', s)
    s = re.sub(r'(\d{4}年\d{1,2}月)日', r'\1', s)
    s = re.sub(r'([,，。、；;])[,，。、；;]+', r'\1', s)
    s = re.sub(r'\s+([，。；：、？！）》”])', r'\1', s)
    s = re.sub(r'([（《“])\s+', r'\1', s)
    return s.strip()


INLINE_OPT = re.compile(r'(?<![A-Za-z0-9])([A-D])\s*[.．、]\s*')


def split_inline_opts(line):
    """一行里塞了多个选项时拆成多行（2022/2023 扫描卷常见）"""
    hits = [m for m in INLINE_OPT.finditer(line)]
    if len(hits) < 2:
        return [line]
    parts, prev = [], None
    for m in hits:
        if prev is not None:
            parts.append(line[prev:m.start()].strip())
        prev = m.start()
    head = line[: hits[0].start()].strip()
    parts.append(line[prev:].strip())
    out = []
    if head:
        out.append(head)
    out.extend(parts)
    return out


OCR_CACHE = Path(__file__).parent / '.cache/po-ocr'


def ocr_cached(year, which):
    f = OCR_CACHE / f'{year}.json'
    if not f.exists():
        raise SystemExit(f'缺 OCR 缓存 {f}，先跑 ocr-politics.py {year}')
    return json.loads(f.read_text(encoding='utf-8'))[which]


def page_text(pg, ocr=False):
    if ocr:
        dpi = 300
        pix = pg.get_pixmap(dpi=dpi)
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            pix.save(f.name)
            tmp = f.name
        out = tmp + '.out'
        subprocess.run(['tesseract', tmp, out, '-l', 'chi_sim', '--psm', '6'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        txt = Path(out + '.txt').read_text(encoding='utf-8', errors='ignore')
        Path(tmp).unlink(missing_ok=True)
        Path(out + '.txt').unlink(missing_ok=True)
        return txt
    return pg.get_text()


def doc_lines(doc, ocr=False, year=None, which='paper'):
    if ocr and year:
        raw_text = '\n'.join(ocr_cached(year, which))
        source = [raw_text]
    else:
        source = [page_text(pg, False) for pg in doc]
    lines = []
    for page in source:
        for raw in page.split('\n'):
            line = norm(raw)
            if not line:
                continue
            if FOOTER_PAT.search(line) and len(line) < 40:
                continue
            lines.extend(split_inline_opts(fix_text(line)))
    return lines


# 题号被 OCR 认错时，题干开头会多出一个怪字（菇2001 / 丑我国 / 廷2009 / 虴胡锦涛…）
JUNK_HEAD = set('菇丑廷虴姪姑逕赵赴迦蛤虬士亏焉島岛乌乌龭虍虺')

HEADER_CONT = re.compile(r'(小题|答题卡|涂黑|共\s*\d+\s*分|四个选项|题目要求|注意事项|考生|试题册)')

ANSWER_MARK = re.compile(r'[\[【（(]\s*(?:标准)?答案(要点)?\s*[\]】）)Jj]?')
NOISE_MARK = re.compile(r'[\[【（(]\s*(分数|考点|选项|解析|考点点拨|命题分析)\s*[\]】）)]')
SKIP_MARK = re.compile(r'^[\[【（(]\s*(分数|选项|考点|答案要点)\s*[\]】）)]?')
ESSAY_ANS = re.compile(r'[\[【（(]\s*(?:参考)?(?:答案|解析)(要点)?\s*[\]】）)]')
QSUB_ESSAY = re.compile(r'^[(（]\s*[0-9]\s*[)）].*([？?]|[（(]\s*\d+\s*分\s*[)）])')
QSUB_Q = re.compile(r'^[(（]\s*([0-9])\s*[)）]')


DEC_SPLIT = re.compile(r'(\d)\s*[.．]\s+(\d)')


def clean_stem(s):
    s = re.sub(r'^\s*\d{1,3}\s*[.．、:：]\s*', '', s)
    if s and s[0] in JUNK_HEAD and (len(s) > 1 and (s[1].isdigit() or '\u4e00' <= s[1] <= '\u9fff')):
        s = s[1:]
    s = DEC_SPLIT.sub(r'\1.\2', s)
    s = re.sub(r'[（(\s]+$', '', s)
    return s.strip()


def parse_questions(lines):
    """以「选项 A」为锚点切题：A 之前累积的文字属于本题题干"""
    sections = []          # [{kind, questions:[...]}]
    cur_sec = None
    cur = None
    pending = []           # 下一题题干
    in_ans = False
    essay_open = False

    skip_header = [False]

    def new_sec(kind):
        nonlocal cur_sec, cur, pending, in_ans, essay_open
        same = [x for x in sections if x['kind'] == kind and x['questions']]
        if same:
            cur_sec = same[0]
        else:
            cur_sec = {'kind': kind, 'questions': []}
            sections.append(cur_sec)
        cur, in_ans, essay_open = None, False, False
        pending = []
        skip_header[0] = True

    expected = [1]

    def push_q(stem_lines, kind):
        q = {'n': 0, 'sec': kind, 'stem': '', 'options': {}, 'ansbuf': '', 'lines': []}
        q['stem'] = clean_stem(fix_text(''.join(stem_lines)))
        cur_sec['questions'].append(q)
        return q

    for i, line in enumerate(lines):
        if SEC_PAT.match(line):
            head = line[:24]
            if re.search(r'多[项选顶]', head):
                new_sec('multi')
            elif re.search(r'单[项选顶]|单选', head):
                new_sec('single')
            elif '分析' in head or '主观' in head:
                new_sec('essay')
            continue
        if cur_sec is None:
            continue

        if cur_sec['kind'] == 'essay':
            # 只认「下一个该出现的题号」，且题号后不能紧跟数字（排除「38.9%」这种表格数据）
            nxt = 34 + len([q for q in cur_sec['questions'] if q.get('_num')])
            m = re.match(r'^\s*(\d{2})\s*[.．、]\s*([^\d].*)$', line)
            if m and int(m.group(1)) == nxt and nxt <= 38:
                cur = push_q([m.group(2)], 'essay')
                cur['_num'] = int(m.group(1))
                cur['_sub'] = 1
                if m.group(2).strip():
                    cur['lines'].append(m.group(2).strip())
                continue
            if cur is not None:
                text = fix_text(line)
                mm = ESSAY_ANS.search(text)
                if mm:
                    # 【参考答案】之后是解析册内容，不能混进材料/小问
                    pre, post = text[:mm.start()].strip(), text[mm.end():].strip()
                    if pre:
                        cur.setdefault('lines', []).append(pre)
                        cur['stem'] = (cur['stem'] + pre).strip()
                    cur['_ans'] = True
                    if post:
                        cur.setdefault('ans', []).append(post)
                    continue
                if cur.get('_ans'):
                    # 答案区里出现下一小问（(2)…）就切回题干；用序号递增判定，避免把答案里的「(1)」误当小问
                    msub = QSUB_Q.match(text)
                    if msub and int(msub.group(1)) == cur.get('_sub', 1):
                        cur['_sub'] = int(msub.group(1)) + 1
                        cur['_ans'] = False
                        cur.setdefault('lines', []).append(text)
                        cur['stem'] = (cur['stem'] + text).strip()
                    else:
                        cur.setdefault('ans', []).append(text)
                else:
                    msub = QSUB_Q.match(text)
                    if msub and int(msub.group(1)) == cur.get('_sub', 1):
                        cur['_sub'] = int(msub.group(1)) + 1
                    cur.setdefault('lines', []).append(text)
                    cur['stem'] = (cur['stem'] + text).strip()
            continue

        if skip_header[0]:
            if HEADER_CONT.search(line) or (SEC_PAT.match(line) is None and len(line) < 6 and not OPT_PAT.match(line)):
                continue
            skip_header[0] = False
        if SKIP_MARK.match(line):
            continue
        if ANSWER_MARK.search(line) or NOISE_MARK.search(line):
            in_ans = True
            if cur is not None and ANSWER_MARK.search(line):
                seg = line[ANSWER_MARK.search(line).end():]
                mm = re.match(r'[\s:：]*([A-D](?:[\s、,，]*[A-D]){0,3})(?![A-Za-z])', seg)
                if mm and not cur['ansbuf']:
                    cur['ansbuf'] = re.sub(r'[^A-D]', '', mm.group(1))
            continue

        # 题干 / 选项尾部与下一题号粘连（「…地位24.开放是人类…」）：在原题号处切开
        if cur_sec['kind'] in ('single', 'multi') and not in_ans and not Q_PAT.match(line):
            mm = re.search(r'(?<=[\u4e00-\u9fff）)"”])\s*(\d{1,2})\s*[.．、:：]\s*' + AFTER_NUM, line)
            if mm and int(mm.group(1)) == expected[0] and mm.start() > 0:
                head = fix_text(line[:mm.start()].strip())
                if head:
                    last = cur.get('_last_opt') if cur is not None else None
                    if last:
                        # 题号前那段是上一题「最后一个选项」被折行切掉的尾巴
                        # （例：选项 D「…增强岛内和海外反独促」+ 下一行「统力量的信心和勇气33:…」）
                        cur['options'][last] = (cur['options'][last] + head).strip()
                    else:
                        pending.append(head)
                line = line[mm.start():].strip()

        mo = OPT_PAT.match(line)
        if not mo and cur is not None and len(line) > 2:
            # OCR 漏掉「B.」的句点（B坚持以人民为中心），按字母顺序补齐
            seq_keys = sorted(cur['options'])
            nxt = chr(ord(seq_keys[-1]) + 1) if seq_keys else 'A'
            if line[0].upper() == nxt and not line[1].isascii() and not line[1].isspace():
                mo = OPT_PAT.match(line[0] + '.' + line[1:])
                if mo:
                    line = line[0] + '.' + line[1:]
        if mo:
            letter = mo.group(1).upper()
            body = fix_text(line[mo.end():])
            start = False
            if letter == 'A':
                start = cur is None or len(cur['options']) >= 3 or (cur['options'] and cur.get('_anchored'))
            else:
                # 两栏排版时选项常被打乱（C / A / D / B），D 之后仍有题干文字即视为新题
                start = bool(pending) and (cur is None or bool(cur['options'].get('D')))
            if start:
                cur = push_q(pending, cur_sec['kind'])
                pending = []
            elif cur is None:
                continue
            elif letter == 'A' and not cur['options'] and cur.get('_numbered'):
                cur['options'] = {}
            in_ans = False
            cur['options'][letter] = cur['options'].get(letter, '') + body
            cur['_last_opt'] = letter
            continue

        if not in_ans and cur_sec['kind'] in ('single', 'multi'):
            mq = Q_PAT.match(line)
            if mq:
                num = int(mq.group(1))
                # 某一题的题号在 OCR 里丢了，expected 会卡住：只要上一题选项已齐，就接受更大的题号
                ok = num == expected[0] or (
                    cur is not None and len(cur['options']) >= 3 and expected[0] < num <= expected[0] + 5)
                if ok:
                    rest = line[mq.end():].strip()
                    if pending and cur is not None and cur['options'].get('D'):
                        # 折行把上一题选项切成两半（「…增强岛内和海外反独促」+「统力量的信心和勇气」）
                        last = cur.get('_last_opt') or sorted(cur['options'])[-1]
                        cur['options'][last] = (cur['options'][last] + ''.join(pending)).strip()
                        pending = []
                    cur = push_q([rest] if rest else [], cur_sec['kind'])
                    cur['_numbered'] = True
                    expected[0] = num + 1
                    pending = []
                    continue

        if in_ans:
            ql = Q_LOOSE.match(line)
            if ql:
                num = int(ql.group(1))
                # expected 会因为前面某题走「选项锚点」路径而滞后，这里放宽几题容差
                if expected[0] <= num <= expected[0] + 6:
                    in_ans = False
                    expected[0] = num
                    pending = [line]
            continue

        if cur is None:
            pending.append(line)
            continue
        if cur['options'].get('D'):
            pending.append(line)
            continue
        last = cur.get('_last_opt')
        if last:
            cur['options'][last] = (cur['options'][last] + fix_text(line)).strip()
        else:
            cur['stem'] = (cur['stem'] + fix_text(line)).strip()

    # 收尾：编号顺序化、选项按字母排序、清理空题
    for sec in sections:
        keep = []
        for q in sec['questions']:
            q.pop('_last_opt', None)
            q['options'] = {k: q['options'][k] for k in sorted(q['options'])}
            if not q['stem'] and not q['options']:
                continue
            if not q['options'] and re.fullmatch(r'[A-D]{1,4}', q['stem']):
                continue   # 卷末答案速查表被当成题干
            if not q['stem'] and len(q['options']) < 3 and keep and len(keep[-1]['options']) >= 3:
                continue   # 跨页错位的选项碎片（没有题干、选项也不全）
            keep.append(q)
        for idx, q in enumerate(keep, 1):
            q['n'] = idx
        sec['questions'] = keep
    return sections


def answers_from(text):
    """解析册答案：先按「题号+标记」，再按出现顺序兜底"""
    by_num, seq = {}, []
    for m in ANSWER_MARK.finditer(text):
        seg = text[m.end():m.end() + 40]
        # 答案可能是「A B D」（2020 版式用空格分隔），也可能是「ABD」
        am = re.match(r'[\s:：]*([A-D](?:[\s、,，]*[A-D]){0,3})(?![A-Za-z])', seg)
        if not am:
            continue
        ans = re.sub(r'[^A-D]', '', am.group(1))
        head = text[max(0, m.start() - 12):m.start()]
        nm = re.search(r'(\d{1,2})\s*[.．、]?\s*$', head)
        seq.append(ans)
        if nm:
            n = int(nm.group(1))
            if n not in by_num:
                by_num[n] = ans
    return by_num, seq


INLINE_ANS = [
    re.compile(r'[（(]\s*([A-D]{1,4})\s*[)）]'),
    re.compile(r'正确选项(?:为|是)?\s*[:：]?\s*([A-D])'),
    re.compile(r'本题(?:应)?选\s*[:：]?\s*([A-D])'),
    re.compile(r'答案(?:为|是)?\s*[:：]?\s*([A-D])'),
]


def answers_inline(sol_text, pats=None):
    """解析册把答案写在题干末尾（2022/2023 版式）：按出现顺序取 (C)，再用题号锚点补缺号"""
    pats = pats or [INLINE_ANS[0]]
    seq, anchors, cur = [], {}, None
    for raw in sol_text.split('\n'):
        s = raw.strip()
        if not s:
            continue
        m = re.match(r'^(\d{1,2})\s*[.．、]\s*', s)
        if m and 1 <= int(m.group(1)) <= 38:
            cur = int(m.group(1))
        hit = None
        for pat in pats:
            mm = pat.search(s)
            if mm:
                hit = mm.group(1)
                break
        if hit is None:
            continue
        seq.append(hit)
        if cur is not None and cur not in anchors:
            anchors[cur] = len(seq) - 1
    out = {n: seq[i] for n, i in anchors.items()}
    # 题号被 OCR 吞掉时该题没有锚点：用相邻锚点之间的顺序位置补齐
    nums = sorted(anchors)
    for a, b in zip(nums, nums[1:]):
        gap = [n for n in range(a + 1, b) if n not in out]
        idx = list(range(anchors[a] + 1, anchors[b]))
        if gap and len(gap) == len(idx):
            for n, i in zip(gap, idx):
                out[n] = seq[i]
    return out


# 少数题目的选项在原卷里被 PD F 抽成跨页错位（2020 第 10 题 A/C 跑到别处），按版面人工补齐
MANUAL_OPT = {
    (2020, 10): {'A': '要不要以革命手段推翻清王朝', 'C': '要不要进行社会革命'},
}


# 个别题目在原卷 PDF 里题干被裁掉（页边界丢行 / 文本层缺失），按原页图片补齐
MANUAL_STEM = {
    (2020, 'single', 9): '近代以来中华民族面临着争取民族独立、人民解放和实现国家富强、人民富裕两大历史任务。'
                         '近代中国的历史表明,要争得民族独立和人民解放,必须首先',
    (2022, 'multi', 11): '1935年1月中共中央政治局在长征途中召开的遵义会议,是党的历史上的一个生死攸关的转折点。这次会议',
    (2023, 'multi', 3): '马克思的平均利润理论深刻阐明了资本主义社会利润转化为平均利润以及剩余价值被进一步分割的原理。'
                        '在利润率平均化的过程中,仍然能获得平均利润的资本有',
    (2023, 'multi', 11): '1905年至1907年间,围绕中国社会变革问题,资产阶级革命派与改良派分别以《民报》《新民丛报》为主要舆论阵地,'
                         '展开了一场论战。这场论战',
}


def build(year, probe=False):
    paper_file, sol_file = PAPERS[year]
    pdoc = pymupdf.open(SRC / paper_file)
    has_text = sum(len(p.get_text().strip()) for p in pdoc) > 2000
    plines = doc_lines(pdoc, ocr=not has_text, year=year, which='paper')
    sections = parse_questions(plines)

    sdoc = pymupdf.open(SRC / sol_file)
    s_text = ''.join(p.get_text() for p in sdoc)
    has_stext = len(s_text.strip()) > 3000
    if not has_stext:
        s_text = '\n'.join(ocr_cached(year, 'sol'))
    by_num, seq = answers_from(norm(s_text))
    if len(by_num) < 34:
        inline = answers_inline(s_text)
        if len(inline) < 30:
            for n, v in answers_inline(s_text, INLINE_ANS).items():
                inline.setdefault(n, v)
        for n, v in inline.items():
            by_num.setdefault(n, v)

    for sec in sections:
        for q in sec['questions']:
            patch_stem = MANUAL_STEM.get((year, sec['kind'], q['n']))
            if patch_stem:
                q['stem'] = patch_stem
            q['stem'] = re.sub(r'[（(\s]+$', '', q['stem']).strip()

    mc = [q for sec in sections if sec['kind'] in ('single', 'multi') for q in sec['questions']]
    for idx, q in enumerate(mc, 1):
        patch = MANUAL_OPT.get((year, idx))
        if patch:
            for k, v in patch.items():
                q['options'].setdefault(k, v)
            q['options'] = {k: q['options'][k] for k in sorted(q['options'])}
        ans = q.get('ansbuf') or by_num.get(idx) or ''
        if not ans and len(seq) >= idx:
            ans = seq[idx - 1]
        q['answer'] = ans.upper()

    info = {s['kind']: len(s['questions']) for s in sections}
    miss = [q['n'] for q in mc if not q['answer']]
    bad_opt = [q['n'] for q in mc if len(q['options']) < 4]

    if probe:
        print(f'\n===== {year}  文本层={has_text} 解析文本={has_stext}  单选{info.get("single",0)} 多选{info.get("multi",0)} 分析{info.get("essay",0)}')
        for sec in sections:
            if sec['kind'] != 'single':
                continue
            for q in sec['questions'][:2]:
                print(f"  Q{q['n']} [{q['answer']}] {q['stem'][:50]}")
                for k, v in q['options'].items():
                    print(f"     {k}. {v[:34]}")
        print('  缺答案:', miss, ' 选项不足:', bad_opt[:10])
    return sections, mc, miss, bad_opt


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    probe = '--probe' in sys.argv
    years = [int(a) for a in args] or sorted(PAPERS)
    for y in years:
        build(y, probe=True)
