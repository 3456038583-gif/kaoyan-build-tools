/* 知识库首页：搜索（懒加载 search.json）+ 类型筛选 */
(function () {
  const input = document.getElementById('q');
  const results = document.getElementById('results');
  const browse = document.getElementById('browse');
  const chipsBox = document.getElementById('chips');
  if (!input || !results || !browse) return;

  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const escRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  let index = null;
  let loading = null;
  let activeType = '';

  function load() {
    if (index) return Promise.resolve(index);
    if (!loading) {
      loading = fetch('/library/search.json')
        .then(r => r.json())
        .then(d => { index = d; return d; })
        .catch(() => { index = []; return index; });
    }
    return loading;
  }

  /* 类型筛选按钮：从页面上的笔记行里收集 */
  const types = new Map();
  document.querySelectorAll('#browse [data-type]').forEach(el => {
    const t = el.getAttribute('data-type');
    if (t) types.set(t, (types.get(t) || 0) + 1);
  });
  if (types.size > 1) {
    const entries = [...types.entries()].sort((a, b) => b[1] - a[1]);
    chipsBox.innerHTML = `<button type="button" data-type="" class="on">全部</button>` +
      entries.map(([t, n]) => `<button type="button" data-type="${esc(t)}">${esc(t)} ${n}</button>`).join('');
    chipsBox.addEventListener('click', e => {
      const b = e.target.closest('button');
      if (!b) return;
      activeType = b.dataset.type || '';
      chipsBox.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
      run();
    });
  } else {
    chipsBox.innerHTML = '';
  }

  function highlight(text, terms) {
    let out = esc(text);
    for (const t of terms) {
      if (!t) continue;
      out = out.replace(new RegExp(escRe(esc(t)), 'gi'), m => `<mark>${m}</mark>`);
    }
    return out;
  }

  function run() {
    const q = input.value.trim();
    if (!q && !activeType) {
      results.hidden = true;
      results.innerHTML = '';
      browse.hidden = false;
      return;
    }
    load().then(list => {
      const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
      const scored = [];
      for (const it of list) {
        if (activeType && it.y !== activeType) continue;
        const title = it.t.toLowerCase();
        const hay = `${it.t} ${it.k} ${it.a} ${it.h} ${it.g} ${it.x}`.toLowerCase();
        let ok = true;
        let score = 0;
        for (const term of terms) {
          if (!hay.includes(term)) { ok = false; break; }
          if (title.includes(term)) score += 100;
          if ((it.k || '').toLowerCase().includes(term)) score += 20;
        }
        if (!ok) continue;
        if (!terms.length) score = 1;
        scored.push({ it, score });
      }
      scored.sort((a, b) => b.score - a.score || a.it.t.localeCompare(b.it.t, 'zh-CN'));
      browse.hidden = true;
      results.hidden = false;
      if (!scored.length) {
        results.innerHTML = `<p class="result-empty">没有找到匹配的笔记。</p>`;
        return;
      }
      const limit = 80;
      results.innerHTML = `<p class="result-empty">共 ${scored.length} 条${scored.length > limit ? `，显示前 ${limit} 条` : ''}</p>` +
        scored.slice(0, limit).map(({ it }) =>
          `<a class="result" href="${esc(it.u)}">
             <span class="r-title">${highlight(it.t, terms)}</span>
             <span class="badge">${esc(it.y || '')}</span>
             <span class="r-path">${esc(it.g || '')}</span>
           </a>`).join('');
    });
  }

  let timer = 0;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(run, 120);
  });
  input.addEventListener('focus', load);

  document.addEventListener('keydown', e => {
    if (e.key === '/' && document.activeElement !== input) {
      e.preventDefault();
      input.focus();
    } else if (e.key === 'Escape' && document.activeElement === input) {
      input.value = '';
      run();
      input.blur();
    }
  });
})();
