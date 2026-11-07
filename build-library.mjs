#!/usr/bin/env node
/**
 * 把 Obsidian 仓库 Lazy-Kaoyan-Library 构建成静态知识库。
 *
 * 用法：node build-library.mjs
 * 可通过 VAULT_DIR / SITE_DIR 环境变量覆盖默认路径。
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import yaml from 'js-yaml';
import katex from 'katex';
import { marked } from 'marked';

const VAULT = process.env.VAULT_DIR || '/Users/feikntn111/Documents/macobsidian/Lazy-Kaoyan-Library';
const SITE = process.env.SITE_DIR || '/Users/feikntn111/File_no_iCloud/kaoyan-website/kaoyan-hub';
const OUT = path.join(SITE, 'library');
const TOOLS = path.dirname(new URL(import.meta.url).pathname);

const IMAGE_RE = /\.(png|jpe?g|gif|svg|webp|avif)$/i;
const report = { dead: [], images: [], math: [], notes: [], warn: [] };

/* ───────────────────────────── 基础工具 ───────────────────────────── */

const esc = s => String(s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');
const escAttr = esc;
const stripTags = s => String(s)
  .replace(/<[^>]*>/g, '')
  .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"').replace(/&#39;/g, "'");

function cmpNatural(a, b) {
  const ra = String(a).match(/\d+|\D+/g) || [];
  const rb = String(b).match(/\d+|\D+/g) || [];
  for (let i = 0; i < Math.min(ra.length, rb.length); i++) {
    const x = ra[i], y = rb[i];
    if (x === y) continue;
    const nx = /^\d+$/.test(x), ny = /^\d+$/.test(y);
    if (nx && ny) return Number(x) - Number(y);
    return x.localeCompare(y, 'zh-CN');
  }
  return ra.length - rb.length;
}

function walk(dir, rel = '') {
  const out = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true })
    .filter(e => !e.name.startsWith('.'))
    .sort((a, b) => cmpNatural(a.name, b.name));
  for (const e of entries) {
    const r = rel ? `${rel}/${e.name}` : e.name;
    const abs = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(abs, r));
    else out.push({ rel: r, abs, name: e.name });
  }
  return out;
}

/* ─────────────────────────── frontmatter ─────────────────────────── */

function looseFrontmatter(text) {
  const fm = {};
  for (const line of text.split('\n')) {
    const m = /^([A-Za-z_][\w-]*):[ \t]*(.*)$/.exec(line);
    if (!m) continue;
    let v = m[2].trim();
    v = v.replace(/^"(.*)"$/, '$1').replace(/^'(.*)'$/, '$1');
    fm[m[1]] = v;
  }
  return fm;
}

function parseNote(file) {
  let raw = fs.readFileSync(file.abs, 'utf8');
  const hadBOM = raw.charCodeAt(0) === 0xfeff;
  if (hadBOM) raw = raw.slice(1);
  let fm = {}, body = raw, yamlError = null;
  const m = /^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/.exec(raw);
  if (m) {
    try {
      const v = yaml.load(m[1]);
      if (v && typeof v === 'object' && !Array.isArray(v)) fm = v;
    } catch (e) {
      yamlError = e.message.split('\n')[0];
      fm = looseFrontmatter(m[1]);
    }
    body = raw.slice(m[0].length);
  }
  return { fm, body, hadBOM, yamlError };
}

function strings(v) {
  if (v == null) return [];
  if (Array.isArray(v)) return v.map(x => String(x).trim()).filter(Boolean);
  return String(v).split(/[,，]/).map(x => x.trim()).filter(Boolean);
}

function cleanTitle(v) {
  if (Array.isArray(v)) v = v[0];
  if (typeof v !== 'string') return '';
  let s = v.replace(/<%[\s\S]*?%>/g, '').trim();
  const m = /^\[\[([\s\S]*?)\]\]$/.exec(s);
  if (m) s = m[1].split('|')[0].split('#')[0].trim();
  return s;
}

/* ─────────────────────────── 扫描与索引 ─────────────────────────── */

const files = walk(VAULT);
const mdFiles = files.filter(f => f.name.toLowerCase().endsWith('.md'));
const imgFiles = files.filter(f => IMAGE_RE.test(f.name));

const notes = mdFiles.map(f => {
  const dir = path.posix.dirname(f.rel) === '.' ? '' : path.posix.dirname(f.rel);
  const base = path.posix.basename(f.name, path.posix.extname(f.name));
  const { fm, body, hadBOM, yamlError } = parseNote(f);
  const title = cleanTitle(fm.title) || base;
  const type = String(fm.type || fm.note_type || fm.kind || '').trim();
  const tags = strings(fm.tags);
  const aliases = strings(fm.aliases).map(a => cleanTitle(a) || a).filter(Boolean);
  return {
    rel: f.rel, dir, base, body, fm, title, type, tags, aliases,
    hadBOM, yamlError,
    outRel: null, url: null, headings: [], headingByPlain: new Map(), headingByNorm: new Map(), headingByMathless: new Map(),
  };
});

const byRel = new Map();
const byBase = new Map();
const byAlias = new Map();
const byStripped = new Map();

function stripNumbering(s) {
  return String(s).replace(/^\d+(?:[.．\-]\d+)*[\s._、-]*/u, '').trim();
}
function normKey(s) {
  return String(s).replace(/[\s_\-.·、,，:：;；'"“”‘’()（）[\]【】]/g, '').toLowerCase();
}

for (const n of notes) {
  byRel.set(n.rel.replace(/\.md$/i, ''), n);
  if (!byBase.has(n.base)) byBase.set(n.base, n);
  for (const a of n.aliases) if (!byAlias.has(a)) byAlias.set(a, n);
  const s = stripNumbering(n.base);
  if (s && !byStripped.has(s)) byStripped.set(s, n);
}

// 有编号前缀的标题/别名也可以被无编号的写法找到（[[高斯公式]] → 10-7 高斯公式）
for (const n of notes) {
  for (const cand of [n.base, n.title, ...n.aliases]) {
    const s = stripNumbering(cand);
    if (s && !byStripped.has(s)) byStripped.set(s, n);
  }
}

/* ─────────────────────── 输出路径 & 目录树 ─────────────────────── */

function slugSegment(seg) {
  return seg.replace(/\s+/g, '-').replace(/[#?%&]/g, '').replace(/-+/g, '-');
}

const usedPaths = new Set();
for (const n of notes.sort((a, b) => cmpNatural(a.rel, b.rel))) {
  const segs = n.rel.replace(/\.md$/i, '').split('/').map(slugSegment);
  let relOut = segs.join('/');
  let i = 2;
  while (usedPaths.has(relOut.toLowerCase())) relOut = `${segs.join('/')}-${i++}`;
  usedPaths.add(relOut.toLowerCase());
  n.outRel = relOut;
  // Cloudflare 默认 html_handling=auto-trailing-slash：磁盘上是 .html，对外链接不带扩展名，
  // 既避免每个内链吃一次 307，也保证 canonical 唯一。
  n.url = '/library/' + encodeURI(relOut);
}

const orderedNotes = [...notes].sort((a, b) => cmpNatural(a.rel, b.rel));
orderedNotes.forEach((n, i) => {
  n.prev = orderedNotes[i - 1] || null;
  n.next = orderedNotes[i + 1] || null;
});

/* ───────────────────────────── 标题锚点 ───────────────────────────── */

function headingPlain(raw) {
  return String(raw)
    .replace(/!\[\[[^\]]*\]\]/g, '')
    .replace(/\[\[([^\]|#]*)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]/g, (m, a, b) => b || a)
    .replace(/\$\$[\s\S]*?\$\$/g, '')
    .replace(/\$[^$\n]*\$/g, '')
    .replace(/@@[^@\n]*@@/g, '');
}
function headingIdClean(raw) {
  return headingId(headingPlain(raw));
}

function headingId(raw) {
  let s = String(raw)
    .replace(/\[\[([^\]|#]*)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]/g, (m, a, b) => b || a)
    .replace(/!\[\[[^\]]*\]\]/g, '')
    .replace(/<[^>]*>/g, '')
    .replace(/[`*_~=]/g, '')
    .replace(/[\\/#?%^&{}[\]()'"“”‘’]/g, ' ');
  s = s.replace(/\s+/g, '-').replace(/-+/g, '-').replace(/^[-.]+|[-.]+$/g, '');
  return s || 'section';
}

function scanHeadings(md) {
  const lines = md.split('\n');
  const out = [];
  let fence = null;
  for (const line of lines) {
    const f = /^\s*(```+|~~~+)/.exec(line);
    if (f) {
      if (!fence) fence = f[1][0];
      else if (f[1][0] === fence) fence = null;
      continue;
    }
    if (fence) continue;
    const m = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
    if (m) out.push({ level: m[1].length, raw: m[2], id: headingIdClean(m[2]) });
  }
  const used = new Map();
  for (const h of out) {
    const n = used.get(h.id) || 0;
    used.set(h.id, n + 1);
    if (n) h.id = `${h.id}-${n}`;
  }
  return out;
}

for (const n of notes) {
  n.headings = scanHeadings(n.body);
  for (const h of n.headings) {
    if (!n.headingByPlain.has(h.raw)) n.headingByPlain.set(h.raw, h.id);
    const k = normKey(h.raw);
    if (!n.headingByNorm.has(k)) n.headingByNorm.set(k, h.id);
    // 链接里的锚点是「渲染后的标题」，公式只剩 $S_n$ 之类的字面量：再按去掉公式的文本建一份索引
    const km = normKey(headingPlain(h.raw));
    if (!n.headingByMathless) n.headingByMathless = new Map();
    if (!n.headingByMathless.has(km)) n.headingByMathless.set(km, h.id);
  }
}

/* ─────────────────────── 渲染器（Obsidian 语法） ─────────────────────── */

const CALLOUT_LABEL = {
  tip: '提示', note: '笔记', quote: '引用', abstract: '摘要', success: '要点',
  example: '例子', info: '信息', summary: '小结', help: '帮助', warning: '注意',
  question: '问题', caution: '小心', attention: '注意', danger: '警告', failure: '失败',
  bug: '问题', todo: '待办', important: '重要', hint: '提示', check: '完成',
};

// 收集全库标签（frontmatter + 正文行内 #标签），用于把行内标签渲染成小徽章
const tagSet = new Set();
for (const n of notes) for (const t of n.tags) tagSet.add(t);
for (const n of notes) {
  const re = /(^|[^\w一-鿿])(#[\p{L}][\p{L}\p{N}_/-]*)/gu;
  let m;
  while ((m = re.exec(n.body))) {
    const t = m[2].slice(1);
    if (!/^\d+$/.test(t)) tagSet.add(t);
  }
}
const tagList = [...tagSet].filter(t => t.length > 1).sort((a, b) => b.length - a.length);

marked.setOptions({ gfm: true, breaks: false, mangle: false, headerIds: false });

const mdRenderer = new marked.Renderer();
mdRenderer.heading = function (text, level, raw) {
  // 用原始 Markdown 算 id：text 里可能残留占位符 token（如 `## 联想[[x]]`）
  const src = (raw && raw.trim()) ? raw : text;
  const id = headingIdClean(src);
  return `<h${level} id="${escAttr(id)}">${text}</h${level}>`;
};
marked.use({ renderer: mdRenderer });

function imageUrl(file) {
  const hash = crypto.createHash('sha1').update(file.rel).digest('hex').slice(0, 8);
  const safe = file.name.replace(/\s+/g, '-');
  const dir = path.join(OUT, 'assets');
  fs.mkdirSync(dir, { recursive: true });
  const dest = path.join(dir, `${hash}-${safe}`);
  if (!fs.existsSync(dest)) fs.copyFileSync(file.abs, dest);
  return '/library/assets/' + encodeURI(`${hash}-${safe}`);
}

function resolveImage(note, target) {
  const t = target.trim().replace(/^\.\//, '');
  const candidates = [];
  if (t.includes('/')) {
    candidates.push(path.posix.normalize(path.posix.join(note.dir, t)));
    candidates.push(path.posix.normalize(t));
  } else {
    candidates.push(path.posix.join(note.dir, 'fig', t));
    candidates.push(path.posix.join(note.dir, t));
    candidates.push(t);
  }
  for (const c of candidates) {
    const hit = imgFiles.find(f => f.rel === c);
    if (hit) return hit;
  }
  const byName = imgFiles.filter(f => f.name === t || path.posix.basename(f.rel) === t);
  return byName[0] || null;
}

function findBlock(body, id) {
  // 找到以 ^id 结尾的块；callout 取整个引用块，其余取紧邻的非空段落
  const lines = body.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const m = /(^|\s)\^([A-Za-z0-9][A-Za-z0-9-]*)\s*$/.exec(lines[i]);
    if (!m || m[2] !== id) continue;
    if (lines[i].startsWith('>')) {
      let a = i, b = i;
      while (a > 0 && lines[a - 1].startsWith('>')) a--;
      while (b < lines.length - 1 && lines[b + 1].startsWith('>')) b++;
      return lines.slice(a, b + 1).join('\n');
    }
    let a = i, b = i;
    while (a > 0 && lines[a - 1].trim() !== '') a--;
    while (b < lines.length - 1 && lines[b + 1].trim() !== '') b++;
    return lines.slice(a, b + 1).join('\n');
  }
  return null;
}

function findSection(body, heading) {
  const lines = body.split('\n');
  const norm = normKey(heading);
  let start = -1, level = 0, fence = null;
  for (let i = 0; i < lines.length; i++) {
    const f = /^\s*(```+|~~~+)/.exec(lines[i]);
    if (f) { fence = fence ? null : f[1][0]; continue; }
    if (fence) continue;
    const m = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(lines[i]);
    if (!m) continue;
    if (start < 0) {
      if (normKey(m[2]) === norm) { start = i; level = m[1].length; }
    } else if (m[1].length <= level) {
      return lines.slice(start, i).join('\n');
    }
  }
  return start >= 0 ? lines.slice(start).join('\n') : null;
}

function renderNoteBody(note, md, opts = {}) {
  const { depth = 0, visited = new Set([note.rel]), origin = note } = opts;
  const cid = 'P' + Math.random().toString(36).slice(2, 10);
  const store = [];
  const put = html => { store.push(html); return `@@${cid}_${store.length - 1}@@`; };

  let s = md.replace(/\r\n?/g, '\n');

  /* 1. Templater */
  s = s.replace(/<%[\s\S]*?%>/g, () => put('<span class="tpl">〔模板变量〕</span>'));

  /* 2. 围栏代码块 / dataview */
  s = s.replace(/^```([^\n`]*)\n([\s\S]*?)^```[ \t]*$/gm, (m, lang, code) => {
    if (/^\s*dataview/i.test(lang)) {
      const query = esc(code.replace(/\s+$/, ''));
      return put(`<div class="dataview"><div class="dv-head">Dataview 动态查询</div><p class="dv-note">该查询依赖 Obsidian 的 Dataview 插件，静态网页无法执行。</p><details><summary>查看原始查询</summary><pre><code>${query}</code></pre></details></div>`);
    }
    return put(`<pre class="code"><code>${esc(code.replace(/\s+$/, ''))}</code></pre>`);
  });
  s = s.replace(/^~~~([^\n~]*)\n([\s\S]*?)^~~~[ \t]*$/gm,
    (m, lang, code) => put(`<pre class="code"><code>${esc(code.replace(/\s+$/, ''))}</code></pre>`));

  /* 3. 行内代码 */
  s = s.replace(/`([^`\n]+)`/g, (m, c) => put(`<code>${esc(c)}</code>`));

  /* 4. Callout（先剥掉 `> ` 前缀，正文递归渲染，里面的公式/嵌入才能正常处理） */
  s = transformCallouts(s, body => renderNoteBody(note, body, { depth, visited, origin }));

  /* 5. 公式（$$…$$ 与 $…$ 一起扫描，允许出现在行中间/跨行） */
  s = renderMath(s, (html) => put(html), note);

  /* 6. 块 ID */
  // 独占一行的 `^id`：锚点放在上一块之后
  s = s.replace(/^[ \t]*\^([A-Za-z0-9][A-Za-z0-9-]*)[ \t]*$/gm,
    (m, id) => `<span class="bid" id="${escAttr(id)}"></span>`);
  s = s.replace(/^([^\n]*?)[ \t]\^([A-Za-z0-9][A-Za-z0-9-]*)[ \t]*$/gm, (m, pre, id) => {
    if (!pre.trim()) return m;
    return `${pre} <span class="bid" id="${escAttr(id)}"></span>`;
  });

  /* 7. 思维导图伪标题 `- ## 小节` / `- ### 小节` …（Obsidian 允许把标题写进列表项） */
  s = s.replace(/^(\s*)[-*]\s+(#{1,6})\s+(.+)$/gm,
    (m, pad, hashes, text) => `${pad}- <span class="mm-h mm-h${hashes.length}">${text}</span>`);

  /* 8. 高亮 ==x== */
  s = s.replace(/==([^=\n]+)==/g, '<mark>$1</mark>');

  /* 9. 嵌入 */
  s = s.replace(/!\[\[([^\]\n]+)\]\]/g, (m, inner) => {
    const [rawTarget, rawAttrs] = inner.split('|');
    const target = rawTarget.trim();
    const width = (rawAttrs || '').trim();
    if (IMAGE_RE.test(target)) {
      const img = resolveImage(note, target);
      if (!img) {
        report.images.push(`${note.rel}: ${target}`);
        return put(`<div class="missing-img">图片缺失：${esc(target)}</div>`);
      }
      const style = /^\d+$/.test(width) ? ` style="max-width:${Number(width)}px"` : '';
      return put(`<figure class="note-fig"><img src="${escAttr(imageUrl(img))}" alt="${escAttr(path.posix.basename(target))}"${style} loading="lazy"><figcaption>${esc(path.posix.basename(target))}</figcaption></figure>`);
    }
    // 笔记嵌入
    const [notePart, ...anchorParts] = target.split('#');
    const anchor = anchorParts.join('#');
    const resolved = resolveNote(notePart, note);
    if (!resolved) {
      report.dead.push(`${note.rel}: ![[${target}]]`);
      return put(`<span class="deadlink">![[${esc(target)}]]</span>`);
    }
    const tgt = resolved;
    if (depth >= 3 || visited.has(tgt.rel)) {
      return put(`<div class="embed"><div class="embed-src">↪ <a href="${escAttr(tgt.url)}">${esc(tgt.title)}</a></div></div>`);
    }
    let src = null;
    if (!anchor) src = tgt.body;
    else if (anchor.startsWith('^')) src = findBlock(tgt.body, anchor.slice(1));
    else src = findSection(tgt.body, anchor);
    if (!src) src = tgt.body;
    const innerHtml = renderNoteBody(tgt, src, {
      depth: depth + 1,
      visited: new Set([...visited, tgt.rel]),
      origin,
    });
    if (origin !== tgt) addBacklink(tgt.rel, origin);
    return put(`<div class="embed"><div class="embed-src">↪ 嵌入自 <a href="${escAttr(tgt.url)}">${esc(tgt.title)}</a></div>${innerHtml}</div>`);
  });

  /* 10. 普通 wikilink */
  s = s.replace(/\[\[([^\]\n]+)\]\]/g, (m, inner) => {
    const [rawTarget, rawAlias] = inner.split('|');
    const target = rawTarget.trim();
    const alias = rawAlias && rawAlias.trim();
    const [notePart, ...anchorParts] = target.split('#');
    const anchor = anchorParts.join('#');
    const resolved = resolveNote(notePart, note);
    /* 块引用 [[笔记#^id]] 没有可读文字，用目标笔记标题；标题锚点仍然只显示标题文字 */
    const anchorLabel = anchor && !anchor.startsWith('^') ? anchor : '';
    const shown = alias || anchorLabel || (resolved ? resolved.title : target);
    if (!resolved) {
      report.dead.push(`${note.rel}: [[${target}]]`);
      return put(`<span class="deadlink" title="仓库中未找到：${escAttr(target)}">${esc(shown)}</span>`);
    }
    if (origin !== resolved) addBacklink(resolved.rel, origin);
    let frag = '';
    if (anchor) {
      if (anchor.startsWith('^')) frag = '#' + encodeURIComponent(anchor.slice(1));
      else {
        const norm = normKey(anchor);
        const id = resolved.headingByPlain.get(anchor) || resolved.headingByNorm.get(norm)
          || (resolved.headingByMathless && resolved.headingByMathless.get(normKey(headingPlain(anchor))))
          || headingIdClean(anchor);
        frag = '#' + encodeURIComponent(id);
      }
    }
    return put(`<a class="wl" href="${escAttr(resolved.url + frag)}">${esc(shown)}</a>`);
  });

  /* 11. 行内标签（必须放在 wikilink 之后，否则 `[[#标题]]` 里的 # 会被误当成标签） */
  if (tagList.length) {
    const tagRegex = new RegExp(`(^|[^\\w\\u4e00-\\u9fff#="])#(${tagList.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})(?![\\w\\u4e00-\\u9fff/-])`, 'gu');
    s = s.replace(tagRegex, (m, pre, tag) => `${pre}<span class="tag">#${tag}</span>`);
  }

  /* 12. marked */
  let html = marked.parse(s);
  html = html.replace(new RegExp(`<p>\\s*@@${cid}_(\\d+)@@\\s*</p>`, 'g'), (m, i) => store[Number(i)]);
  html = html.replace(new RegExp(`@@${cid}_(\\d+)@@`, 'g'), (m, i) => store[Number(i)]);
  return html;
}

/* 统一的公式扫描：从左到右，优先识别 $$…$$，否则 $…$。
   允许 $$ 出现在行中间（如 `则$$A^T A = …$$`），也允许跨行；
   `$$$` 这种连写会自然拆成「关闭 + 开启」，与 Obsidian 的读法一致。 */
function renderMath(s, put, note) {
  let out = '';
  let i = 0;
  const n = s.length;
  while (i < n) {
    const ch = s[i];
    if (ch === '\\' && s[i + 1] === '$') { out += '\\$'; i += 2; continue; }
    if (ch !== '$') { out += ch; i++; continue; }

    if (s[i + 1] === '$') {
      let j = i + 2;
      let closed = -1;
      while (j < n - 1) {
        if (s[j] === '\\') { j += 2; continue; }
        if (s[j] === '$' && s[j + 1] === '$') { closed = j; break; }
        j++;
      }
      if (closed > i + 2) {
        const tex = s.slice(i + 2, closed);
        if (tex.trim() && !tex.includes('@@')) {
          out += put(mathHtml(tex, true, note));
          i = closed + 2;
          continue;
        }
      }
      out += '$$';
      i += 2;
      continue;
    }

    let j = i + 1;
    let closed = -1;
    while (j < n) {
      if (s[j] === '\\') { j += 2; continue; }
      if (s[j] === '$') { closed = j; break; }
      j++;
    }
    if (closed > i + 1) {
      const tex = s.slice(i + 1, closed);
      if (tex.trim() && !/\n[ \t]*\n/.test(tex) && !tex.includes('@@')) {
        out += put(mathHtml(tex, false, note));
        i = closed + 1;
        continue;
      }
    }
    out += '$';
    i++;
  }
  return out;
}

/* KaTeX 字体里没有圈码 ①—⑳，直接渲染会变成豆腐块；换成 (1)—(20) */
function fixCircled(tex) {
  return tex.replace(/[①-⑳]/g, (c) => `(${c.charCodeAt(0) - 0x2460 + 1})`);
}

function mathHtml(tex, display, note) {
  let rendered;
  try {
    rendered = katex.renderToString(fixCircled(tex), {
      displayMode: display,
      throwOnError: true,
      strict: false,
      trust: true,
      maxSize: 12,
      macros: { '\\R': '\\mathbb{R}' },
    });
  } catch (e) {
    report.math.push(`${note ? note.rel : '?'}: ${String(e.message).split('\n')[0].slice(0, 120)} | ${tex.replace(/\s+/g, ' ').slice(0, 90)}`);
    return `<span class="math-error" title="${escAttr(tex.replace(/\s+/g, ' '))}">${esc(tex)}</span>`;
  }
  return display ? `<div class="math-display">${rendered}</div>` : rendered;
}

function transformCallouts(text, renderBody) {
  const lines = text.split('\n');
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const m = /^>\s*\[!([^\]]+)\]([+-])?[ \t]*(.*)$/.exec(lines[i]);
    if (!m) { out.push(lines[i]); continue; }
    const body = [];
    let j = i + 1;
    for (; j < lines.length; j++) {
      const l = lines[j];
      if (/^>/.test(l)) body.push(l.replace(/^>[ \t]?/, ''));
      else if (l.trim() === '' && j + 1 < lines.length && /^>/.test(lines[j + 1])) body.push('');
      else break;
    }
    let blockId = null;
    if (body.length) {
      const last = body[body.length - 1];
      const bm = /(^|\s)\^([A-Za-z0-9][A-Za-z0-9-]*)\s*$/.exec(last);
      if (bm) {
        blockId = bm[2];
        body[body.length - 1] = last.slice(0, bm.index);
      }
    }
    const typeRaw = m[1].trim();
    const type = typeRaw.toLowerCase().replace(/[^a-z]/g, '') || 'note';
    const fold = m[2] === '-';
    const title = (m[3] || '').trim() || CALLOUT_LABEL[type] || typeRaw;
    // 标题里可能有公式（`> [!tip] 常用结论 $(a>0)$`），必须走同一套行内渲染，
    // 直接 esc 会把 `>` 变成 `&gt;`，公式就废了。
    const titleHtml = renderBody(title)
      .replace(/^<p>([\s\S]*)<\/p>\s*$/, '$1')
      .trim() || esc(title);
    const inner = renderBody(body.join('\n'));
    const idAttr = blockId ? ` id="${escAttr(blockId)}"` : '';
    if (fold) {
      out.push(`<details class="callout callout-${type}"${idAttr}><summary>${titleHtml}</summary><div class="callout-body">${inner}</div></details>`);
    } else {
      out.push(`<div class="callout callout-${type}"${idAttr}><div class="callout-title">${titleHtml}</div><div class="callout-body">${inner}</div></div>`);
    }
    i = j - 1;
  }
  return out.join('\n');
}

function resolveNote(target, fromNote) {
  let t = String(target).trim();
  if (!t) return fromNote;
  if (byBase.has(t)) return byBase.get(t);
  if (byAlias.has(t)) return byAlias.get(t);
  if (t.includes('/')) {
    const p1 = path.posix.normalize(path.posix.join(fromNote.dir, t));
    if (byRel.has(p1)) return byRel.get(p1);
    const p2 = path.posix.normalize(t);
    if (byRel.has(p2)) return byRel.get(p2);
    const b = path.posix.basename(t);
    if (byBase.has(b)) return byBase.get(b);
  }
  const s = stripNumbering(t);
  if (s && byStripped.has(s)) return byStripped.get(s);
  if (byRel.has(path.posix.normalize(t)) && !t.endsWith('/')) return byRel.get(path.posix.normalize(t));
  return null;
}

/* ───────────────────────────── 反向链接 ───────────────────────────── */

const backlinks = new Map(); // rel -> Set(origin rel)
function addBacklink(targetRel, originNote) {
  if (!targetRel || !originNote || targetRel === originNote.rel) return;
  if (!backlinks.has(targetRel)) backlinks.set(targetRel, new Set());
  backlinks.get(targetRel).add(originNote.rel);
}

/* ───────────────────────────── 页面构建 ───────────────────────────── */

const SITE_NAV = (active) => `
<nav class="sitebar" aria-label="站点导航">
  <a class="sb-brand" href="/">考研资料总库</a>
  <div class="sb-links">
    <a href="/math/"${active === 'math' ? ' class="on"' : ''}>数学真题</a>
    <a href="/exam/"${active === 'exam' ? ' class="on"' : ''}>英语真题</a>
    <a href="/politics/"${active === 'politics' ? ' class="on"' : ''}>政治真题</a>
    <a href="/english/"${active === 'english' ? ' class="on"' : ''}>英语速查</a>
    <a href="/library/"${active === 'library' ? ' class="on"' : ''}>知识库</a>
  </div>
</nav>`;

function crumbs(n) {
  const parts = n.outRel.split('/');
  const dirs = parts.slice(0, -1);
  return `<a href="/library/">知识库</a>` + dirs.map(d => ` <span class="sep">/</span> <span>${esc(d.replace(/-/g, ' '))}</span>`).join('');
}

function renderNotePage(n) {
  const bodyHtml = renderNoteBody(n, n.body);
  const tags = n.tags.map(t => `<span class="tag">#${esc(t)}</span>`).join(' ');
  const aliases = n.aliases.length ? `<span class="aliases">别名：${n.aliases.map(esc).join('、')}</span>` : '';
  const bl = [...(backlinks.get(n.rel) || [])].map(rel => notes.find(x => x.rel === rel)).filter(Boolean);
  const blHtml = bl.length
    ? `<section class="backlinks"><h2>引用本篇</h2><ul>${bl.map(b => `<li><a href="${escAttr(b.url)}">${esc(b.title)}</a></li>`).join('')}</ul></section>`
    : '';
  const pager = `<nav class="pager">
    ${n.prev ? `<a class="pg prev" href="${escAttr(n.prev.url)}"><span>上一篇</span>${esc(n.prev.title)}</a>` : '<span></span>'}
    ${n.next ? `<a class="pg next" href="${escAttr(n.next.url)}"><span>下一篇</span>${esc(n.next.title)}</a>` : '<span></span>'}
  </nav>`;
  const typeBadge = n.type ? `<span class="badge">${esc(n.type)}</span>` : '';
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>${esc(n.title)} · 数学/英语知识库</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/vendor/katex/katex.min.css">
<link rel="stylesheet" href="/site.css">
<link rel="stylesheet" href="/library/note.css">
<script src="/countdown.js" defer></script>
</head>
<body class="note-page">
${SITE_NAV('library')}
<div class="lib-layout">
  <aside class="lib-side" id="libSide" aria-label="知识库目录">
    <div class="side-head">
      <a href="/library/">数学/英语知识库</a>
      <button type="button" class="side-toggle" id="sideToggle" aria-expanded="false">目录</button>
    </div>
    <div class="side-search">
      <input id="sideQ" type="search" placeholder="搜索笔记…" autocomplete="off" aria-label="搜索笔记">
      <div class="side-results" id="sideResults" hidden></div>
    </div>
    <div class="side-tree" id="sideTree"></div>
  </aside>
  <main class="note-main">
    <nav class="crumbs">${crumbs(n)}</nav>
    <article class="note-article">
      <header class="note-head">
        ${typeBadge}
        <h1>${esc(n.title)}</h1>
        <div class="note-meta">${tags} ${aliases}</div>
      </header>
      <div class="prose" id="prose">${bodyHtml || '<p class="empty">（本篇暂无内容）</p>'}</div>
      ${blHtml}
      ${pager}
    </article>
  </main>
  <aside class="note-toc" aria-label="本篇目录"><div class="toc-title">本篇目录</div><div id="toc"></div></aside>
</div>
<script src="/library/note.js"></script>
<script src="/library/note-search.js" defer></script>
</body>
</html>`;
}

/* 目录树 JSON */
function buildTree() {
  const root = { name: '知识库', path: '', dirs: new Map(), notes: [] };
  for (const n of orderedNotes) {
    const parts = n.outRel.split('/').slice(0, -1);
    let node = root;
    let acc = '';
    for (const p of parts) {
      acc = acc ? `${acc}/${p}` : p;
      if (!node.dirs.has(p)) node.dirs.set(p, { name: p.replace(/-/g, ' '), path: acc, dirs: new Map(), notes: [] });
      node = node.dirs.get(p);
    }
    node.notes.push({ t: n.title, u: n.url, y: n.type, p: n.outRel });
  }
  const ser = node => ({
    n: node.name,
    p: node.path,
    d: [...node.dirs.values()].sort((a, b) => cmpNatural(a.name, b.name)).map(ser),
    f: node.notes.map(x => ({ t: x.t, u: x.u, y: x.y, p: x.p })),
  });
  return ser(root);
}

const tree = buildTree();

/* 搜索索引 */
const searchIndex = orderedNotes.map(n => {
  const text = n.body
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/\$\$[\s\S]*?\$\$/g, ' ')
    .replace(/\$[^$\n]+\$/g, ' ')
    .replace(/!\[\[[^\]]*\]\]/g, ' ')
    .replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (m, a, b) => b || a)
    .replace(/<[^>]*>/g, ' ')
    .replace(/[#>*_`~]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return {
    t: n.title,
    u: n.url,
    p: n.outRel,
    g: n.dir,
    y: n.type,
    k: n.tags.join(' '),
    a: n.aliases.join(' '),
    h: n.headings.map(h => h.raw).join(' '),
    x: text.slice(0, 1200),
  };
});

/* 知识库首页 */
const COLLECTIONS = [
  { id: 'gaoshu', label: '高等数学', subject: 'math', match: /^数一\/1-高数\// },
  { id: 'xiandai', label: '线性代数', subject: 'math', match: /^数一\/2-线代\// },
  { id: 'gailv', label: '概率论', subject: 'math', match: /^数一\/3-概率论\// },
  { id: 'yingyi', label: '英语一', subject: 'english', match: /^英一\// },
  { id: 'moban', label: '模板与说明', subject: 'english', match: /^(模版文件夹\/|README)/ },
];

function groupIntoChapters(list) {
  /* 目录结构：数一 / 1-高数 / 2-一元函数微分学 / … / 笔记
     去掉第一段（科目）后，第二段才是「章」，如 1 函数 极限与连续、6 二次型 */
  const chapters = new Map();
  for (const n of list) {
    const rest = n.outRel.split('/').slice(1);
    const chapter = rest.length > 2 ? rest[1].replace(/-/g, ' ') : '未分章';
    if (!chapters.has(chapter)) chapters.set(chapter, []);
    chapters.get(chapter).push(n);
  }
  return [...chapters.entries()].sort((a, b) => cmpNatural(a[0], b[0]));
}

const noteLi = (n) =>
  `<li><a href="${escAttr(n.url)}" data-type="${escAttr(n.type)}"><span class="li-title">${esc(n.title)}</span>${n.type ? `<span class="badge">${esc(n.type)}</span>` : ''}</a></li>`;

let libraryIndex = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>知识库 · 考研资料总库</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/site.css">
<link rel="stylesheet" href="/library/note.css">
<script src="/countdown.js" defer></script>
</head>
<body class="lib-index">
${SITE_NAV('library')}
<div class="lib-wrap">
  <header class="lib-mast">
    <div class="lib-seal">库</div>
    <div>
      <p class="lib-kicker">LAZY KAOYAN LIBRARY</p>
      <h1>数学 · 英语 · 政治 知识库</h1>
      <p class="lib-sub">${notes.length + 1} 篇笔记 · 高数 ${notes.filter(n => COLLECTIONS[0].match.test(n.outRel)).length} · 线代 ${notes.filter(n => COLLECTIONS[1].match.test(n.outRel)).length} · 概率论 ${notes.filter(n => COLLECTIONS[2].match.test(n.outRel)).length} · 英语一 ${notes.filter(n => COLLECTIONS[3].match.test(n.outRel)).length} · 模板 ${notes.filter(n => COLLECTIONS[4].match.test(n.outRel)).length} · 政治 1</p>
    </div>
  </header>

  <div class="lib-tabs" role="tablist" aria-label="科目筛选">
    <button class="lib-tab on" type="button" data-scope="all" role="tab" aria-selected="true">全部</button>
    <button class="lib-tab" type="button" data-scope="math" role="tab" aria-selected="false">数学</button>
    <button class="lib-tab" type="button" data-scope="english" role="tab" aria-selected="false">英语</button>
    <button class="lib-tab" type="button" data-scope="politics" role="tab" aria-selected="false">政治</button>
  </div>

  <div class="lib-search">
    <input id="q" type="search" placeholder="搜索标题、标签、正文…" autocomplete="off" aria-label="搜索笔记">
    <div class="chips" id="chips"></div>
  </div>
  <section id="results" class="results" hidden></section>

  <div id="browse">
`;

for (const col of COLLECTIONS) {
  const list = orderedNotes.filter(n => col.match.test(n.outRel));
  if (!list.length) continue;
  libraryIndex += `<section class="lib-col" id="${col.id}" data-subject="${col.subject || 'math'}"><h2>${col.label}<small>${list.length} 篇</small></h2>`;
  const chapters = groupIntoChapters(list);
  /* 单章的分组（英语一、模板）不用折叠框，直接把条目铺开 */
  if (chapters.length === 1) {
    libraryIndex += `<ul class="plain">`;
    for (const n of chapters[0][1]) libraryIndex += noteLi(n);
    libraryIndex += `</ul>`;
  } else {
    for (const [chapter, ns] of chapters) {
      libraryIndex += `<details class="chapter" open><summary><span class="ch-name">${esc(chapter)}</span><span class="ch-count">${ns.length}</span></summary><ul>`;
      for (const n of ns) libraryIndex += noteLi(n);
      libraryIndex += `</ul></details>`;
    }
  }
  libraryIndex += `</section>`;
}

libraryIndex += `
  <section class="lib-col" id="politics" data-subject="politics" hidden>
    <h2>政治<small>1 篇</small></h2>
    <ul class="plain">
      <li><a href="/library/政治/一页纸.html"><span class="li-title">27 考研政治一页纸 · 知识点手册</span><span class="badge">基础知识</span></a></li>
      <li><a href="/pdfs/politics/27-yiyeye.pdf" target="_blank" rel="noopener"><span class="li-title">27 考研政治一页纸 · 知识点手册（原版 PDF）</span><span class="badge">PDF</span></a></li>
      <li><a href="/politics/"><span class="li-title">考研政治真题练习（2010—2026）</span><span class="badge">真题</span></a></li>
    </ul>
  </section>
  </div>
  <footer class="lib-foot">
    <p>内容来自 Obsidian 仓库 Lazy-Kaoyan-Library，静态化后仅供复习查阅。</p>
    <p><a href="/">返回资料总库</a></p>
  </footer>
</div>
<script src="/library/index.js"></script>
<script>
(function () {
  var tabs = [].slice.call(document.querySelectorAll('.lib-tab'));
  var cols = [].slice.call(document.querySelectorAll('.lib-col'));
  function show(scope) {
    tabs.forEach(function (t) {
      var on = t.dataset.scope === scope;
      t.classList.toggle('on', on);
      t.setAttribute('aria-selected', String(on));
    });
    cols.forEach(function (c) {
      c.hidden = scope !== 'all' && c.dataset.subject !== scope;
    });
    if (scope !== 'all') history.replaceState(null, '', '#' + scope);
  }
  tabs.forEach(function (t) {
    t.addEventListener('click', function () { show(t.dataset.scope); });
  });
  var h = (location.hash || '').replace('#', '');
  if (['math', 'english', 'politics'].indexOf(h) >= 0) show(h);
})();
</script>
</body>
</html>`;

/* ───────────────────────────── 写文件 ───────────────────────────── */

/* 政治一页纸是同目录里另有脚本生成的（build-onepage.py），重建时先备份再还原 */
const politicsDir = path.join(OUT, '政治');
const politicsBak = path.join(TOOLS, '.politics-bak');
if (fs.existsSync(politicsDir)) {
  fs.rmSync(politicsBak, { recursive: true, force: true });
  fs.cpSync(politicsDir, politicsBak, { recursive: true });
}
fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });
if (fs.existsSync(politicsBak)) {
  fs.cpSync(politicsBak, politicsDir, { recursive: true });
  fs.rmSync(politicsBak, { recursive: true, force: true });
}

// 样式与脚本
for (const f of ['note.css', 'note.js', 'index.js', 'note-search.js']) {
  fs.copyFileSync(path.join(TOOLS, 'templates', f), path.join(OUT, f));
}

// 笔记页
for (const n of orderedNotes) {
  const dest = path.join(OUT, n.outRel + '.html');
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, renderNotePage(n), 'utf8');
}

fs.writeFileSync(path.join(OUT, 'index.html'), libraryIndex, 'utf8');
fs.writeFileSync(path.join(OUT, 'nav.json'), JSON.stringify(tree), 'utf8');
/* 政治一页纸（build-onepage.py 生成）也并入搜索索引 */
const onePage = path.join(OUT, '政治', '一页纸.html');
if (fs.existsSync(onePage)) {
  const text = fs.readFileSync(onePage, 'utf8')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;|&amp;|&lt;|&gt;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const dup = searchIndex.findIndex(x => x.u === '/library/政治/一页纸.html');
  if (dup >= 0) searchIndex.splice(dup, 1);
  searchIndex.push({
    t: '27 考研政治一页纸 · 知识点手册',
    u: '/library/政治/一页纸.html',
    p: '政治/一页纸',
    g: '政治',
    y: '基础知识',
    k: '政治 一页纸 知识点',
    a: '',
    h: '考研政治 一页纸 知识点手册 马原 毛中特 史纲 思修 时政',
    x: text.slice(0, 3000),
  });
}
fs.writeFileSync(path.join(OUT, 'search.json'), JSON.stringify(searchIndex), 'utf8');

/* 回写首页统计 */
const hubPath = path.join(SITE, 'index.html');
if (fs.existsSync(hubPath)) {
  let hub = fs.readFileSync(hubPath, 'utf8');
  const stats = {
    notes: notes.length + 1,   // + 政治一页纸手册
    gaoshu: notes.filter(n => COLLECTIONS[0].match.test(n.outRel)).length,
    xiandai: notes.filter(n => COLLECTIONS[1].match.test(n.outRel)).length,
    gailv: notes.filter(n => COLLECTIONS[2].match.test(n.outRel)).length,
    yingyi: notes.filter(n => COLLECTIONS[3].match.test(n.outRel)).length,
    moban: notes.filter(n => COLLECTIONS[4].match.test(n.outRel)).length,
  };
  hub = hub.replace(/data-stat="(\w+)">[^<]*</g, (m, k) => `data-stat="${k}">${stats[k] ?? ''}<`);
  fs.writeFileSync(hubPath, hub, 'utf8');
}

/* 报告 */
const lines = [];
lines.push(`笔记 ${notes.length} 篇，图片引用 ${report.images.length} 处缺失`);
if (report.dead.length) {
  lines.push('', `未解析的 wikilink ${report.dead.length} 处：`);
  lines.push(...report.dead.map(x => '  ' + x));
}
if (report.images.length) {
  lines.push('', '缺失图片：', ...report.images.map(x => '  ' + x));
}
if (report.math.length) {
  lines.push('', `KaTeX 渲染失败 ${report.math.length} 处（页面显示原始 LaTeX 灰框）：`, ...report.math.map(x => '  ' + x));
}
const bomNotes = notes.filter(n => n.hadBOM);
if (bomNotes.length) lines.push('', `带 BOM 的文件 ${bomNotes.length} 个：`, ...bomNotes.map(n => '  ' + n.rel));
const yamlErr = notes.filter(n => n.yamlError);
if (yamlErr.length) lines.push('', 'YAML 解析失败（已降级）：', ...yamlErr.map(n => `  ${n.rel} — ${n.yamlError}`));
const noFM = notes.filter(n => !n.body && !Object.keys(n.fm).length);
fs.writeFileSync(path.join(TOOLS, 'build-report.txt'), lines.join('\n') + '\n', 'utf8');

console.log(`✓ ${notes.length} 篇笔记 → ${OUT}`);
console.log(`  未解析链接 ${report.dead.length} 处，缺失图片 ${report.images.length} 处`);
console.log(`  报告：${path.join(TOOLS, 'build-report.txt')}`);
