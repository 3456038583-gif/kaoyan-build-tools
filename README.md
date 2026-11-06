# build-tools · 考研资料站构建脚本

把 Obsidian 仓库 `~/Documents/macobsidian/Lazy-Kaoyan-Library` 预渲染成静态笔记页，
写进发布目录 `~/File_no_iCloud/kaoyan-website/kaoyan-hub/library/`，同时把统计数字回写到总库首页。

这个目录负责生成主站 `kaoyan-hub` 里所有「不是手写」的内容：知识库、英语真题页、政治真题页、政治一页纸。
脚本里的绝对路径按 `~/File_no_iCloud/kaoyan-website/` 这种目录布局写死，换机器时用
`SITE_DIR` 环境变量覆盖输出目录，或直接改文件头部的常量。

## 依赖

```bash
cd ~/File_no_iCloud/kaoyan-website/build-tools
npm install          # marked / katex / js-yaml，版本见 package.json
```

## 重建知识库

```bash
cd ~/File_no_iCloud/kaoyan-website/build-tools
node build-library.mjs
```

- 输入：`$VAULT_DIR`（默认 `~/Documents/macobsidian/Lazy-Kaoyan-Library`）
- 输出：`$SITE_DIR/library/`（默认 `~/File_no_iCloud/kaoyan-website/kaoyan-hub`）
- 报告：`build-report.txt`（未解析链接、缺失图片、BOM/YAML 降级清单）
- 每次运行会**整个删除并重建** `library/`，该目录不要手改。

## 部署

```bash
cd ~/File_no_iCloud/kaoyan-website/kaoyan-hub
NODE_OPTIONS=--dns-result-order=ipv4first npx wrangler@latest deploy
```

本机 Node 解析 IPv6 会让 wrangler `fetch failed`，必须带 `--dns-result-order=ipv4first`。
`pdfs/`、`figs/`、`vendor/` 内容不变时 wrangler 会复用已上传资源，不会重传 900 MB。

## 站点结构

```
kaoyan-hub/
├─ index.html          总库首页（data-stat 占位符由构建脚本回写）
├─ site.css            全站顶栏 .sitebar
├─ math/index.html     数学真题（原根目录 index.html 迁入）
├─ english/index.html  英一答案速查（来自 ../sources/英一答案速查.html）
├─ library/            构建产物：258 篇笔记 + index/nav.json/search.json
├─ app.js data*.js meta*.js   仍留在根目录
└─ pdfs/ figs/ vendor/       原样不动
```

URL 规则：磁盘上是 `<笔记名>.html`，对外链接不带 `.html`（Cloudflare `html_handling`
默认 `auto-trailing-slash`，`/foo.html` 会 307 到 `/foo`）。

## 发布目录里被改过的「源文件」

`/math/` 与独立数学站 `../kaoyan-math-standalone/` 共用同一套 `app.js` / `data.js`，唯一区别是路径：
独立站用相对路径（`pdfs/…`），主站迁到子目录后必须用绝对路径（`/pdfs/…`）。两边改功能后要同步，
只差下面这几个补丁：

| 文件 | 位置 | 改动 |
|---|---|---|
| `app.js` | `paperPath` / `reviewPath` | `` `pdfs/…` `` → `` `/pdfs/…` `` |
| `app.js` | `suppPdf.paper` / `suppPdf.sol` | `'pdfs/supplement/…'` → `'/pdfs/supplement/…'` |
| `app.js` | 补充真题两个 `data-pdf="…"` | 同上加 `/` |
| `app.js` | `FIG_RE` 替换处 | `<img src="/${src.trim()…">` |
| `data.js` | `YEAR_FILES` | `` `/data${y}.js` ``、`` `/meta${y}.js` `` |
| `math/index.html` | KaTeX 三处 + `data.js`/`app.js` | 全部改成 `/vendor/…`、`/data.js`、`/app.js` |

`math/index.html` 由 `../kaoyan-math-standalone/index.html` 复制而来，源文件用的是 KaTeX CDN 且没有站点导航条；
主站版本改成本地 `vendor/katex/`、加了 `.sitebar`，并给各处 sticky 顶距补上 `var(--sb-h)`，差别仅此。

## 已知项

- 4 张图片在 Obsidian 仓库里本就缺失（`fig/绝对值不等式.png`、`fig/脱帽法.png`、
  `fig/1.2 极限.png`、`fig/1.2 极限-1.png`），页面上显示虚线占位框。
- 27 处 wikilink 指向仓库中不存在的笔记（含源笔记里写错的锚点），渲染成不可点的灰字。
- Dataview 查询在静态页无法执行，统一显示说明 + 原始查询。
- 思维导图里的 `- ## 小节` 渲染成 `.mm-h` 伪标题，不参与本篇目录。

## 公式渲染（2026-11-05 修）

- 统一用 `renderMath()` 扫全文字符流处理 `$…$` / `$$…$$`，行中出现的 `$$…$$`、`$$$\Rightarrow$$$`
  这种连写也能配对（旧实现只认行首 `$$`，所以思维导图里一长串公式会露出原始 LaTeX）。
- 单个公式渲染失败（KaTeX `throwOnError: true`）不中断构建，输出 `.math-error` 灰红虚线框并写入
  `build-report.txt` 的「KaTeX 渲染失败」段；目前 0 处。
- KaTeX 字体没有圈码，`\text{①}` 会变豆腐块，`fixCircled()` 在渲染前把 ①②…⑳ 换成 (1)(2)…(20)。
- 标题目录 / 锚点 id 用 `headingIdClean()`（先剥公式、wikilink、块 ID 再算 id），保证
  `[[笔记#含公式的标题]]` 能跳到对应小节；`[[笔记#^块id]]` 的链接文字用目标笔记标题。
- 长公式放在 `.math-display`（横向可滚动 + 细滚动条），避免撑破正文栏。

## 政治真题（2010—2026）

```bash
python3 build-politics.py --probe          # 只打印解析结果，核对每年 16 + 17 + 5 题、答案是否齐
python3 build-politics.py                  # 写 politics/data/*.js
python3 build-politics-site.py             # 写 politics/*.html + 首页，并把原卷/解析 PDF 复制到 pdfs/politics/
```

- 输入：`~/Desktop/考研政治资料/考研政治真题/<年份>年政治真题/*.pdf`
- 有文本层的年份直接读 PDF；2021—2023 是扫描件，走 RapidOCR（`ocr-politics.py`），
  结果缓存在 `.cache/po-ocr/{year}.json`，删掉缓存重跑会重新识别（400dpi，约 10 分钟/年）
- 解析要点：以「选项 A」为锚点切题 + 题号序列计数器；`FIXES` 表修 OCR 错字
  （单顶→单选、关千→关于…）；解析册把答案写在题干末尾的年份（2022/2023）用
  `answers_inline()` 按出现顺序取 `(C)`，再用题号锚点补缺号
- 页面题号按全卷连续编号：单选 1—16、多选 17—33、分析 34—38（数据里 `n` 已加 offset）
- `MANUAL_OPT` 是极少数原卷选项被 PDF 抽错位时的人工补丁（目前只有 2020 第 10 题）

## 政治一页纸手册

```bash
python3 build-onepage.py
```

- 输入：`~/Desktop/考研政治资料/澄潇宇一页纸/27考研政治一页纸-知识点手册.pdf`
- 输出：`library/政治/一页纸.html`（逐 span 绝对定位，保留原配色）、`assets/*.png`、
  `library/政治/index.html`，并把 PDF 复制到 `pdfs/politics/27-yiyeye.pdf`
- 末尾会把自己的条目并入 `library/search.json`，重复执行不会叠加
- PDF 里有 3 页空白页（2/6/10）会跳过，所以是 35 页里的 32 页

## 英语真题首页

```bash
node build-exam.mjs
```

英语一/英语二两套年份直接并列，点年份即进整套试卷，没有二级标签页。

## 重建顺序

`build-library.mjs` 会整目录重建 `library/`，但它会先把 `library/政治/` 备份再还原，
并把一页纸条目重新并入搜索索引。稳妥的顺序仍是：

```bash
node build-library.mjs          # 知识库
python3 build-onepage.py        # 一页纸（同步搜索索引）
python3 build-politics-site.py  # 政治真题
node build-exam.mjs             # 英语真题
```
