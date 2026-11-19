# UI 交互设计规格（零依赖复刻手册）

本页记录排行榜页面所有非标准组件的**精确规格与实现位置**，供后续开发在别的页面一比一复刻。

## 0. 总原则

- **零依赖**：纯原生 HTML / CSS / JavaScript。没有 React、Vue、Ant Design、Tailwind，也没有任何 UI 组件库。Popover、折叠头、路由、预加载全部手写。
- **动效只碰 `opacity` 与 `transform`**：GPU 友好，不触发布局重排。统一 `180ms` 缓动。
- **移动端优先 + iframe 友好**：所有内部跳转走 hash，不顶破父页面；浮层用 `absolute`/`fixed`，绝不占文档流。
- **响应式**：手机（<768px）保持 412px 横滑卡片；宽屏（≥768px）容器放大到 `min(92vw,1280px)`，卡片改 `auto-fill` 多列网格（每榜 6 列），尺寸随 `vw` 放大但有上限，避免过大。
- **不引库不代表粗糙**：视觉对齐 Ant Design Popover 的白底 / 圆角 / 阴影 / 箭头 / 缩放淡入。

---

## 1. 统计口径 Popover

代码位置：`index.html` 的 `#rate-info` / `#info-popover` / `#popover-mask`，`style.css` 的 `.info-btn / .popover* / .popover-mask`，`app.js` 的 `bindInfo()`。

### DOM 结构

```html
<button class="info-btn" id="rate-info" type="button">统计口径</button>
<div class="popover" id="info-popover" role="dialog">
  <span class="popover-arrow"></span>
  <div class="popover-title">播放量统计口径</div>
  <div class="popover-content"><p>…</p><p>…</p><p>…</p></div>
</div>
<div class="popover-mask" id="popover-mask"></div>
```

### 设计 Token

| 属性 | 值 |
|---|---|
| 容器背景 | `#ffffff` |
| 圆角 | `10px` |
| 阴影 | `0 6px 24px rgba(0,0,0,.16), 0 0 0 1px rgba(0,0,0,.04)` |
| 内边距 | `12px 14px` |
| 宽度 | `264px` |
| 定位 | `position:absolute; top:calc(100% + 8px); right:12px; z-index:50` |
| 箭头 | `12×12px`, `background:#fff`, `transform:rotate(45deg)`, `top:-6px; right:26px`, 左侧+顶部 1px 细阴影 |
| 标题 | `14px / 600 / #18191c`，`margin-bottom:6px` |
| 正文 | `12px / 1.6 / #61666d`，`p` 间距 `4px`，`b` 为 `#18191c` |
| 遮罩 | `position:fixed; inset:0; z-index:45; background:transparent` |

### 动画

```css
.popover{
  opacity:0;
  transform:translateY(-6px) scale(.98);
  transform-origin:top right;
  transition:opacity .18s, transform .18s;
  pointer-events:none;
}
.popover.show{ opacity:1; transform:translateY(0) scale(1); pointer-events:auto; }
.popover-mask{ display:none; }
.popover-mask.show{ display:block; }
```

### 状态机

| 状态 | popover | mask | 触发 |
|---|---|---|---|
| 关闭 | 无 `.show` | 无 `.show` | 初始 / 点按钮（已开）/ 点遮罩 |
| 打开 | `.show` | `.show` | 点「统计口径」按钮 |

按钮 `click` 里必须 `preventDefault() + stopPropagation()`，否则会穿透到遮罩立即关闭。

---

## 2. 详情页滚动折叠头

代码位置：`index.html` 的 `#view-detail` → `#compact-header` + `#detail-scroll`，`style.css` 的 `.detail-scroll / .compact-header`，`app.js` 的 `bindDetailScroll()` 与 `renderDetail()`。

### 行为

- 详情页**整体**是一个滚动容器 `#detail-scroll`（`flex:1; min-height:0; overflow-y:auto; overscroll-behavior:contain`）。
- banner（`.detail-hero`）与榜单 tabs（`.detail-tabs`）都是 `flex:none` 的普通流元素，**随上滑滚出视口**，不固定。
- 当 `scrollTop > 110`，给居中小标题加 `.show`；回到顶部自动移除。

### 折叠标题 Token

| 属性 | 值 |
|---|---|
| 定位 | `position:absolute; top:28px; left:50%; transform:translateX(-50%); z-index:20` |
| 背景 | `rgba(255,255,255,.96)` |
| 圆角 | `8px` |
| 内边距 | `5px 16px` |
| 字号 | `13px / 600 / #18191c` |
| 阴影 | `0 2px 10px rgba(0,0,0,.15)` |
| 动画 | `opacity .18s`；隐藏时 `opacity:0; pointer-events:none` |

每次 `renderDetail()` 先把 `scrollTop` 归零并移除 `.show`，避免切换榜单后残留折叠态。

---

## 3. Hash 软页面路由

代码位置：`app.js` 的 `parseHash()` / `applyRoute()` / `bindTabs()`。

- 路由形态：`#/` = 首页；`#/rank/<tab>` = 详情页（`tab ∈ up | bgm_season | …`）。
- 两个 view 用 `.view.active` 切换 `display`，**全程不重新加载页面**。
- `hashchange` 监听路由；返回按钮调 `history.back()`。
- 验收：进入详情前后 `window.__softMark` 保持同一值，证明无刷新。

---

## 4. 视口预加载（秒开）

代码位置：`app.js` 的 `observeCards()` / `buildDetailHTML()` / `detailCache` / `prefetched`。

- `IntersectionObserver` 以 `.card-scroller` 为 root，`rootMargin:'0px 240px'`（提前 240px 预取）。
- 卡片进入视口即把该榜单的完整详情 HTML 预生成到 `state.detailCache[idx]`，并 `unobserve`。
- 点击卡片时 `renderDetail(idx)` 直接取缓存 `innerHTML`，无请求、无解析等待。
- 验收：`window.__rankDebug()` 中 `prefetched` 随可见卡片增长，`listLen` 为总条目数。

---

## 5. 紧凑布局 Token（间距收紧基准）

复刻时按这组值取，不要回到大间距版本：

| 区块 | 值 |
|---|---|
| 快捷入口 | `padding:8px 12px 2px; gap:6px; pill 高 34px` |
| 季度行 | `padding:6px 12px 2px; gap:8px` |
| 榜单区块间距 | `clamp(8px,2.4vw,14px)`；标题行上下各 `clamp(3px,1vw,6px)`padding（留白充足，不过紧） |
| 榜单标题行 | 字号 `clamp(12px,3.2vw,15px)`（已缩小），`padding:0 0 0`；无底部导航 |
| 榜单 tabs | `padding:0 clamp(8px,3vw,12px) clamp(4px,1.2vw,7px); gap clamp(3px,1.3vw,5px); pill 高约 22px` |
| 横滑卡片 | `gap:clamp(4px,1.6vw,8px); padding:0 clamp(8px,3vw,12px) 2px; 卡片宽 clamp(100px,29vw,126px); 封面 `aspect-ratio:344/480`; 圆角 6px` |
| 卡片文字 | 标题两行 `clamp(13px,3.6vw,15px)/2行`，副标题两行 `clamp(11px,2.9vw,12px)/2行`，播放量 `clamp(10px,2.7vw,11px)` |
| 横滑边界形变 | 根元素与 `.card-scroller` 均为默认 `overscroll-behavior-x:auto`：**保留原生橡皮筋形变**（到边界继续滑整页有弹性反馈），不要加 none/contain 禁掉它 |
| 封面比例 | 用 Pillow 实测参考图 `1000819990.jpg`（1200×2664）单张封面 **344×480，高/宽=1.40**；CSS 用 `aspect-ratio:344/480`，不用肉眼估。412px 视口下换算为 119×167px |
| 一屏密度（真机 CSS 视口 412×816，对应物理 1240×2447） | 首页 **3 组完整 + 第 4 组露头**（封面 136px / 卡宽 119px，图标不要再压小）；详情页 4 项完整 + 第 5 项露头。每榜只渲染前 20 条 |
| 左右边距 | 统一固定在 `.home-scroll` 的 `padding:0 var(--side) 8px`（`--side:clamp(12px,3.5vw,20px)`），标题/胶囊/卡片左边缘齐平；**不要**把边距做在 `.card-scroller` 上，否则横滑到最左会露出一条缝 |
| 抗卡顿 | 每榜限 20 条（首页约 80 卡）；封面本地化且**不用 lazy 加载**（80 张小图秒显，避免横滑容器 lazy 延迟导致灰块） |
| 详情页列表项 | `item≈134px`；banner `clamp(104px,28vw,134px)`；封面 `clamp(70px,20vw,88px)×clamp(96px,27vw,120px)`；标题单行、评分、标签、简介单行、看正片按钮；`padding:11px` |
| 底部导航 | 高 `52px` |

---

## 6. 复刻验收清单

- [ ] 点「统计口径」弹出白底圆角带箭头阴影的 Popover，180ms 缩放淡入；点遮罩关闭；不占布局
- [ ] 详情页上滑，banner 与 tabs 随之滚走，顶部出现居中「热门榜单」小矩形
- [ ] 点卡片进详情、`history.back()` 返回，全程无刷新（`window` 标记保留）
- [ ] 首页横滑时视口内卡片被预加载，`__rankDebug().prefetched > 0`
- [ ] 卡片间距、榜间距、详情页间距符合第 5 节 Token，无过大留白
- [ ] 无虚构榜单与虚拟用户名；只展示真实的 B 站播放量与 bgm 当季番剧
- [ ] 封面失效时按 `bgm_cover → local_cover → cover` 顺序回退，不出现破图

---

## 7. 一句话结论

**全部手写，零组件库。** 视觉参考 Ant Design Popover，但样式和动画都是本仓库内 200 行以内的原生实现；复刻时直接照搬第 1、2 节的 Token 与状态机即可，不需要引入任何依赖。
