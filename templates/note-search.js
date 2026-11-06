/* 笔记页侧栏常驻搜索：进到任意一节都能直接搜别的笔记 */
(function () {
  const box = document.getElementById('sideQ');
  const out = document.getElementById('sideResults');
  if (!box || !out) return;

  const esc = (s) =>
    String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  let idx = null;
  let loading = false;
  let lastQ = '';
  let hits = [];

  function load() {
    if (idx || loading) return;
    loading = true;
    fetch('/library/search.json', { cache: 'force-cache' })
      .then((r) => r.json())
      .then((d) => {
        idx = Array.isArray(d) ? d : [];
      })
      .catch(() => {
        idx = [];
      })
      .then(() => {
        loading = false;
        if (lastQ) render(lastQ);
      });
  }

  const norm = (s) => String(s || '').toLowerCase();

  function render(q) {
    if (!idx) return;
    const nq = norm(q);
    hits = idx
      .filter(
        (it) =>
          norm(it.t).indexOf(nq) >= 0 ||
          norm(it.p).indexOf(nq) >= 0 ||
          norm(it.h).indexOf(nq) >= 0 ||
          norm(it.k).indexOf(nq) >= 0
      )
      .slice(0, 40);
    if (!hits.length) {
      out.innerHTML = '<p class="sr-empty">没有匹配的笔记</p>';
    } else {
      out.innerHTML = hits
        .map((it, i) => `<a href="${it.u}" data-i="${i}"><b>${esc(it.t)}</b><span>${esc(it.p)}</span></a>`)
        .join('');
    }
    out.hidden = false;
  }

  function run(q) {
    lastQ = q;
    if (!q) {
      out.hidden = true;
      out.innerHTML = '';
      hits = [];
      return;
    }
    if (!idx) {
      load();
      return;
    }
    render(q);
  }

  let timer = 0;
  box.addEventListener('input', () => {
    clearTimeout(timer);
    const q = box.value.trim();
    timer = setTimeout(() => run(q), 110);
  });

  box.addEventListener('focus', load);

  box.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      box.value = '';
      run('');
      box.blur();
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      const first = out.hidden ? null : out.querySelector('a');
      if (first) location.href = first.getAttribute('href');
      else if (hits[0]) location.href = hits[0].u;
    }
  });

  document.addEventListener('click', (e) => {
    if (!out.hidden && !e.target.closest('.side-search')) out.hidden = true;
  });

  /* 预取，让首次输入即出结果 */
  if ('requestIdleCallback' in window) requestIdleCallback(load, { timeout: 2500 });
  else setTimeout(load, 1200);
})();
