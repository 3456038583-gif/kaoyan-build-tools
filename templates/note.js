/* 知识库阅读页：侧边目录（nav.json）、本篇目录、移动端抽屉 */
(function () {
  const decode = s => { try { return decodeURIComponent(s); } catch (e) { return s; } };
  const current = decode(location.pathname)
    .replace(/^\/library\//, '')
    .replace(/\.html$/, '')
    .replace(/\/$/, '');

  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const isUnder = (node, path) => path === node.p || path.startsWith(node.p + '/');

  function renderNode(node, depth) {
    let html = '<ul>';
    for (const d of node.d || []) {
      const open = isUnder(d, current) ? ' open' : '';
      html += `<li class="side-group"><details${open}><summary>${esc(d.n)}</summary>${renderNode(d, depth + 1)}</details></li>`;
    }
    for (const f of node.f || []) {
      const on = f.p === current ? ' on' : '';
      html += `<li><a class="leaf${on}" href="${esc(f.u)}">${esc(f.t)}</a></li>`;
    }
    return html + '</ul>';
  }

  const side = document.getElementById('libSide');
  const treeEl = document.getElementById('sideTree');
  if (treeEl) {
    fetch('/library/nav.json')
      .then(r => r.json())
      .then(tree => { treeEl.innerHTML = renderNode(tree, 0); })
      .catch(() => {});
  }

  const toggle = document.getElementById('sideToggle');
  if (toggle && side) {
    let backdrop = null;
    const close = () => {
      side.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
      if (backdrop) { backdrop.remove(); backdrop = null; }
    };
    toggle.addEventListener('click', () => {
      const open = side.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(open));
      if (open && !backdrop) {
        backdrop = document.createElement('div');
        backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.25);z-index:20';
        backdrop.addEventListener('click', close);
        document.body.appendChild(backdrop);
      } else if (!open) {
        close();
      }
    });
    side.addEventListener('click', e => {
      if (e.target.closest('a')) close();
    });
  }

  /* 本篇目录 */
  const prose = document.getElementById('prose');
  const toc = document.getElementById('toc');
  if (prose && toc) {
    const heads = [...prose.querySelectorAll('h2[id], h3[id]')];
    if (!heads.length) {
      /* 整篇没有小节标题时把右栏整个收掉，比留一个「—」干净 */
      const card = toc.closest('.note-toc');
      if (card) card.style.display = 'none';
    } else {
      toc.innerHTML = heads.map(h =>
        `<a class="${h.tagName === 'H3' ? 'h3' : 'h2'}" href="#${encodeURIComponent(decodeURIComponent(h.id))}">${esc(h.textContent.trim())}</a>`
      ).join('');
      const links = [...toc.querySelectorAll('a')];
      const map = new Map();
      links.forEach((a, i) => {
        const id = decodeURIComponent(a.getAttribute('href').slice(1));
        map.set(heads[i].id, a);
      });
      if ('IntersectionObserver' in window) {
        const io = new IntersectionObserver(entries => {
          for (const en of entries) {
            if (!en.isIntersecting) continue;
            links.forEach(a => a.classList.remove('on'));
            const a = map.get(en.target.id);
            if (a) a.classList.add('on');
          }
        }, { rootMargin: '-10% 0px -75% 0px' });
        heads.forEach(h => io.observe(h));
      }
    }
  }
})();
