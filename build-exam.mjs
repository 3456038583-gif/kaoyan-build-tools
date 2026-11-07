#!/usr/bin/env node
/**
 * 生成 /exam/ 真题库：每套试卷一个页面，进入即试卷（顶部是板块 + 年份条）。
 *   node build-exam.mjs
 * 读取 kaoyan-hub/exam/data/*.js
 * 写 exam/{id}.html、exam/index.html（= 最新一套）、exam/records.html
 */
import fs from 'node:fs';
import path from 'node:path';

const SITE = process.env.SITE_DIR || path.join(process.env.HOME, 'File_no_iCloud/kaoyan-website/kaoyan-hub');
const DATA = path.join(SITE, 'exam/data');

const esc = (s) =>
  String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function loadPaper(file) {
  const src = fs.readFileSync(file, 'utf8');
  const json = src.replace(/^[\s\S]*?window\.__PAPER__\s*=\s*/, '').replace(/;\s*$/, '');
  const p = JSON.parse(json);
  const m = /^(\d{4})-(y[12])$/.exec(p.id || path.basename(file, '.js'));
  if (m) { p.year = Number(m[1]); p.set = m[2]; }
  else console.log(`⚠ ${path.basename(file)} 的 id 不是 YYYY-y1 / YYYY-y2：${p.id}`);
  return p;
}

/** 校验：题目数、答案、选项 */
function validate(p, file) {
  const problems = [];
  const seen = new Set();
  for (const s of p.sections || []) {
    const qs = s.questions || [];
    for (const q of qs) {
      if (seen.has(q.n)) problems.push(`题号重复 ${q.n}`);
      seen.add(q.n);
      const isT = s.kind === 'translation';
      if (!isT && !q.answer) problems.push(`第 ${q.n} 题缺答案`);
      if (!isT && (!q.options || q.options.length !== 4) && s.kind !== 'newtype')
        problems.push(`第 ${q.n} 题选项数 ${q.options ? q.options.length : 0}`);
      if (q.answer && q.options && s.kind !== 'newtype' && s.kind !== 'translation' && !q.options['ABCD'.indexOf(q.answer)])
        problems.push(`第 ${q.n} 题答案 ${q.answer} 越界`);
    }
    for (const para of s.paras || []) {
      if (!para.zh) problems.push(`${s.id} 有段落缺译文`);
    }
  }
  if (problems.length) console.log(`⚠ ${path.basename(file)}\n  - ${problems.join('\n  - ')}`);
  return problems.length;
}

const files = fs.readdirSync(DATA).filter((f) => f.endsWith('.js')).sort();
const papers = [];
let bad = 0;
for (const f of files) {
  const p = loadPaper(path.join(DATA, f));
  bad += validate(p, f);
  papers.push(p);
}

const bySet = { y1: [], y2: [] };
for (const p of papers) (bySet[p.set] ||= []).push(p);
for (const k of Object.keys(bySet)) bySet[k].sort((a, b) => b.year - a.year);

const ALL_YEARS = { y1: [2006, 2026], y2: [2010, 2026] };
const SET_NAME = { y1: '英语（一）', y2: '英语（二）' };
const len = (s) => (bySet[s] || []).length;

const NAV = `<nav class="sitebar" aria-label="站点导航">
  <a class="sb-brand" href="/">考研资料总库</a>
  <div class="sb-links">
    <a href="/math/">数学真题</a>
    <a href="/exam/" class="on">英语真题</a>
    <a href="/politics/">政治真题</a>
    <a href="/english/">英语速查</a>
    <a href="/library/">知识库</a>
  </div>
</nav>`;

const HEAD = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="__DESC__">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@600;700&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
<link rel="stylesheet" href="/site.css">
<link rel="stylesheet" href="/exam/exam.css">
<script src="/countdown.js" defer></script>
</head>
<body>`;

/**
 * 顶部条：板块切换 + 年份（和数学真题一致：进来就是卷子，年份在头上）
 * @param {object} p 当前试卷
 * @param {string} [selfHref] 当前年 chip 的地址（首页为 /exam/）
 */
function barHtml(p, selfHref) {
  const sets = ['y1', 'y2'].filter(len);
  const tabs = sets
    .map((s) => {
      let href;
      if (s === p.set) {
        href = selfHref || `/exam/${p.id}`;
      } else {
        const same = (bySet[s] || []).find((x) => x.year === p.year);
        href = `/exam/${(same || bySet[s][0]).id}`;
      }
      return `<a class="eb-tab${s === p.set ? ' on' : ''}" href="${href}"${s === p.set ? ' aria-current="page"' : ''}>${SET_NAME[s]}</a>`;
    })
    .join('');
  const [lo, hi] = ALL_YEARS[p.set];
  const list = bySet[p.set] || [];
  const chips = [];
  for (let y = hi; y >= lo; y--) {
    const it = list.find((x) => x.year === y);
    if (!it) { chips.push(`<span class="eb-yr off" title="整理中">${y}</span>`); continue; }
    const cur = it.id === p.id;
    const href = cur ? (selfHref || `/exam/${it.id}`) : `/exam/${it.id}`;
    chips.push(`<a class="eb-yr${cur ? ' on' : ''}" href="${href}"${cur ? ' aria-current="page"' : ''} data-id="${it.id}" title="${y} 年${SET_NAME[p.set]}">${y}</a>`);
  }
  return `<div class="ex-bar">
  <div class="ex-bar-in">
    <div class="eb-tabs">${tabs}</div>
    <div class="eb-years" aria-label="年份">${chips.join('')}</div>
    <div class="eb-side"><a class="eb-link" href="/exam/records.html">练习记录</a></div>
  </div>
</div>`;
}

const MARKS_JS = `<script>
/* 已作答的卷子在年份上点一个小标 */
(function () {
  [].forEach.call(document.querySelectorAll('.eb-yr[data-id]'), function (a) {
    try {
      var s = JSON.parse(localStorage.getItem('kaoyan-exam:' + a.dataset.id) || '{}');
      var n = Object.keys(s.picks || {}).length;
      if (n) { a.classList.add('has'); a.title = a.title + ' · 已答 ' + n + ' 题'; }
    } catch (e) {}
  });
})();
</script>`;

/* 首页 = 入口：若记住了上次打开的卷子则跳过去（显式点年份/链接不受影响） */
const POS_JS = (curId) => `<script>
(function(){try{
  var p=JSON.parse(localStorage.getItem('kaoyanExam.position.v1')||'null');
  var id=p&&p.id;
  if(typeof id==='string'&&/^20\\d\\d-y[12]$/.test(id)&&id!=='${curId}'){
    location.replace('/exam/'+id);
  }
}catch(e){}})();
</script>`;

function paperPage(p, selfHref, isEntry) {
  const t = `${p.year} ${p.set === 'y2' ? '英语（二）' : '英语（一）'}`;
  const head = HEAD.replace('__TITLE__', `${t} · 考研英语真题`)
    .replace('__DESC__', `${t} 逐题还原：完形、阅读、新题型、翻译，标注难度与答案，附全文精翻与原始解析 PDF。`)
    .replace('</head>', (isEntry ? POS_JS(p.id) : '') + '</head>');
  return `${head}
${NAV}
${barHtml(p, selfHref)}

<div id="paper"></div>

${MARKS_JS}
<script>window.__PAPERS__=${paperListJson};</script>
<script src="/exam/data/${esc(p.id)}.js"></script>
<script src="/exam/topics.js"></script>
<script src="/exam/essays.js"></script>
<script src="/exam/exam.js"></script>
</body>
</html>
`;
}

/* 所有试卷 id 列表，供试卷页的「切换」菜单用 */
const paperListJson = JSON.stringify(
  [...(bySet.y1 || []), ...(bySet.y2 || [])].map((p) => ({ id: p.id, y: p.year, s: p.set }))
);

for (const p of papers) {
  fs.writeFileSync(path.join(SITE, 'exam', `${p.id}.html`), paperPage(p));
}

/* 首页 = 最新一套英语（一），进来就是试卷；老用户自动跳回上次那套 */
const first = (bySet.y1[0] || papers[0]);
fs.writeFileSync(path.join(SITE, 'exam/index.html'), paperPage(first, '/exam/', true));

/* 练习记录单独一页 */
const recHead = HEAD.replace('__TITLE__', '我的练习记录 · 考研英语真题')
  .replace('__DESC__', '考研英语真题作答记录：各卷客观题得分、正确率与作答进度，保存在本机浏览器。');
fs.writeFileSync(
  path.join(SITE, 'exam/records.html'),
  `${recHead}
${NAV}
${barHtml(first, '/exam/')}

<div class="ex-wrap">
  <header class="ex-mast">
    <div class="ex-seal" aria-hidden="true">英</div>
    <div class="ex-mast-main">
      <p class="kicker">Records · Local Only</p>
      <h1>我的练习记录</h1>
      <p class="ex-sub">
        <span>客观题满分 60</span>
        <span>读完每套卷的作答进度</span>
        <span>只保存在这台设备的浏览器里</span>
      </p>
    </div>
  </header>
  <section class="my-stats" id="myStats"></section>
</div>
<script src="/exam/stats.js"></script>
</body>
</html>
`
);

console.log(
  `✓ exam/index.html = ${first.id}；${papers.length} 套试卷页${bad ? `，${bad} 处校验问题` : '，校验通过'}；records.html 已生成`
);
