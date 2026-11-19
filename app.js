/* 静态番剧排行榜：hash 路由软页面 + 卡片视口预加载 */
(function () {
  'use strict';

  var DATA_URL = 'data/data.json';
  var state = { data: null, season: null, tab: 'up', detailCache: {}, prefetched: {} };

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function tagLine(item, max) {
    max = max || 3;
    return (item.tags || []).slice(0, max).map(function (t) {
      return typeof t === 'string' ? t : (t && (t.name || t.title)) || '';
    }).filter(Boolean).join(' · ');
  }

  function fmt(n) {
    n = Number(n) || 0;
    if (n >= 100000000) return (n / 100000000).toFixed(1) + '亿';
    if (n >= 10000) return (n / 10000).toFixed(1) + '万';
    return String(n);
  }

  function imgSrc(item) {
    // bgm 封面走 anibt 代理；B站封面本地化兜底，最后才用远程直链
    return item.bgm_cover || item.local_cover || item.cover || '';
  }

  function onImgError(img, item) {
    img.onerror = null;
    var fallback = item.local_cover || item.cover;
    if (fallback && img.src.indexOf(fallback) < 0) { img.src = fallback; return; }
    img.style.background = '#e9eaec';
    img.removeAttribute('src');
  }

  function episodesLabel(item) {
    if (item.episodes && item.episodes > 1) return '全 ' + item.episodes + ' 话';
    if (item.episodes === 1) return '更新至 1 话';
    var score = item.bgm_score || item.score;
    if (score) return Number(score).toFixed(1) + ' 分';
    return item.season || '番剧';
  }

  /* ---------------- 渲染：首页卡片 ---------------- */
  function cardHTML(item, idx, tab) {
    var rank = idx + 1;
    var flag = rank <= 3 ? '<span class="rank-flag r' + rank + '">' + rank + '</span>' : '';
    var cover = imgSrc(item);
    var isXifan = !!item.source_id || String(tab || state.tab).indexOf('xifan_') === 0;
    var score = item.bgm_score || item.score;
    var foot = isXifan
      ? (item.score ? fmt(item.score) + ' 热度' : '')
      : (item.views
          ? fmt(item.views) + ' 播放'
          : (score ? Number(score).toFixed(1) + ' 分' : ''));
    return '<a class="card" href="#/rank/' + (tab || state.tab) + '" data-idx="' + idx + '" data-key="' + esc(item.bgm_id || item.title) + '">' +
      '<div class="card-cover">' +
        '<img src="' + esc(cover) + '" alt="" onerror="window.__rankImgErr(this,' + idx + ')">' + flag +
        '<span class="cover-badge">' + episodesLabel(item) + '</span>' +
      '</div>' +
      '<div class="card-title">' + esc(item.title) + '</div>' +
      '<div class="card-sub">' + esc(tagLine(item)) + '</div>' +
      (foot ? '<div class="card-views">' + foot + '</div>' : '') +
    '</a>';
  }

  function currentList() {
    if (!state.data || state.tab === 'pending') return [];
    var list = state.data.rankings[state.tab] || [];
    // 稀饭榜是站点自带榜单，不按本项目季度筛选
    if (state.season && String(state.tab).indexOf('xifan_') !== 0) {
      list = list.filter(function (x) { return x.season === state.season; });
    }
    return list;
  }

  function renderHome() {
    var list = currentList();
    var hot = $('#cards-hot');
    var seasonBox = $('#cards-season');
    var emptyText = state.tab === 'pending'
      ? '该 UP 主数据待接入'
      : '本季度暂无数据，等待下次更新';
    hot.innerHTML = list.length
      ? list.slice(0, 20).map(function (x, i) { return cardHTML(x, i, state.tab); }).join('')
      : '<div style="padding:24px 16px;color:#9499a0;font-size:14px">' + emptyText + '</div>';
    // 当季新番：真实来源 bgm 热度榜
    var bgm = (state.data.rankings.bgm_season || []).filter(function (x) {
      return !state.season || !x.season || x.season === state.season;
    });
    var TOP = 20; // 每榜只渲染前 20，避免几百张图同时加载造成卡顿
    seasonBox.innerHTML = bgm.slice(0, TOP).map(function (x, i) { return cardHTML(x, i, 'bgm_season'); }).join('');

    // 稀饭动漫只在首页留入口，榜单内容在详情页（见 xifanTabHTML/detail-tabs）
    // 累计播放榜：按 views 排序
    var byViews = list.slice().sort(function (a, b) { return (b.views || 0) - (a.views || 0); });
    $('#cards-total').innerHTML = byViews.slice(0, TOP).map(function (x, i) { return cardHTML(x, i, 'up'); }).join('');
    observeCards();
  }

  /* ---------------- 视口预加载 ---------------- */
  var io = null;
  function observeCards() {
    if (io) io.disconnect();
    if (!('IntersectionObserver' in window)) return;
    io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target;
        var idx = Number(el.dataset.idx);
        if (!state.prefetched[idx]) {
          state.prefetched[idx] = true;
          state.detailCache[idx] = buildDetailHTML(currentList(), idx);
        }
        io.unobserve(el);
      });
    }, { root: $('.card-scroller'), rootMargin: '0px 240px' });
    $$('.card').forEach(function (el) { io.observe(el); });
  }

  /* ---------------- 渲染：详情列表 ---------------- */
  function detailItemHTML(item, i) {
    var rank = i + 1;
    var cover = imgSrc(item);
    var tags = (item.tags || []).slice(0, 3).map(function (t) {
      var name = typeof t === 'string' ? t : (t && (t.name || t.title)) || '';
      return name ? '<span class="di-tag">' + esc(name) + '</span>' : '';
    }).join('');
    var isXifan = !!item.source_id || state.tab.indexOf('xifan_') === 0;
    var score = isXifan ? item.score : (state.tab === 'bgm_season' ? item.score : item.bgm_score);
    var scoreHTML = score
      ? '<span class="di-score">' + (isXifan ? fmt(score) + ' 热度' : Number(score).toFixed(1) + ' 分') + '</span>'
      : '';
    var rate = item.play_rate
      ? '<span class="di-tag">' + fmt(item.play_rate) + '/日</span>' : '';
    var link = item.bvid
      ? 'https://www.bilibili.com/video/' + item.bvid
      : (isXifan
          ? 'https://next.xifanacg.com/anime/' + item.source_id
          : (item.bgm_id ? 'https://bgm.tv/subject/' + item.bgm_id : '#/'));
    var views = item.views ? '<span class="di-tag">' + fmt(item.views) + ' 播放</span>' : '';
    var descText = isXifan
      ? (item.note || '数据来自稀饭动漫，仅供参考')
      : (tagLine(item, 5) || 'B站UP主投稿 · 累计播放量统计');
    return '<a class="detail-item" href="' + esc(link) + '" target="_blank" rel="noopener">' +
      '<div class="di-cover">' +
        '<img src="' + esc(cover) + '" alt="" loading="lazy" onerror="window.__rankDetailImgErr(this,' + i + ')">' +
        '<span class="di-rank' + (rank <= 3 ? ' r' + rank : '') + '">' + rank + '</span>' +
      '</div>' +
      '<div class="di-main">' +
        '<div class="di-title">' + esc(item.title) + '</div>' +
        '<div class="di-meta">' + scoreHTML + views + rate + tags + '</div>' +
        '<div class="di-desc">' + esc(descText) + '</div>' +
        '<div class="di-actions">' +
          '<span class="di-play"><b>&#9654;</b> 看正片</span>' +
          '<span class="di-fav">&#9825;</span>' +
        '</div>' +
      '</div>' +
    '</a>';
  }

  function buildDetailHTML(list, focusIdx) {
    return list.map(detailItemHTML).join('');
  }

  // 标题旁外链角标：各数据源可跳原网站（新增站点在 SOURCE_TABS/此处追加即可）
  function updateHero() {
    var t = state.tab;
    var title = 'B站UP主番剧排行榜', desc = '按累计播放量统计', url = '', period = state.data.meta.current_season;
    var src = SOURCE_TABS.filter(function (x) { return x[0] === t; })[0];
    if (src) {
      title = '稀饭动漫 · ' + src[1];
      desc = '数据来自稀饭动漫，仅供参考';
      url = src[2];
    } else if (t === 'bgm_season') {
      title = '当季新番'; desc = '来自 bgm.tv 当季热度';
    } else if (t === 'pending') {
      title = '该 UP 主数据待接入'; desc = '';
    }
    var h1 = $('#hero-title'); if (h1) h1.textContent = title;
    var d = $('#hero-desc'); if (d) d.textContent = desc;
    var p = $('#hero-period'); if (p) p.textContent = period;
    var a = $('#hero-source-link');
    if (a) {
      a.style.display = url ? 'inline-block' : 'none';
      if (url) { a.href = url; a.title = '前往原网站：' + title; }
    }
  }

  function renderDetail(focusIdx) {
    var list = currentList();
    updateHero();
    var hero = state.data.rankings.up[0] || {};
    var bg = hero.bgm_cover || hero.cover || '';
    $('#hero-bg').src = bg;
    $('#hero-period').textContent = state.season || state.data.meta.current_season;
    var html = state.detailCache[focusIdx != null ? focusIdx : 0];
    if (!html) html = buildDetailHTML(list, focusIdx || 0);
    var box = $('#detail-list');
    var scroller = $('#detail-scroll');
    if (scroller) scroller.scrollTop = 0;
    var header = $('#compact-header');
    if (header) header.classList.remove('show');
    if (state.tab === 'pending') {
      box.innerHTML = '<div style="padding:48px 16px;text-align:center;color:#9499a0;font-size:14px">该 UP 主数据待接入</div>';
      return;
    }
    box.innerHTML = html + '<div class="detail-foot">— 到底了 —</div>';
    if (focusIdx != null && focusIdx > 0 && scroller) {
      var target = box.children[focusIdx];
      if (target) scroller.scrollTop = target.offsetTop - 8;
    }
  }

  /* ---------------- 季度 chips ---------------- */
  function upTabHTML(cls) {
    var ups = state.data.meta.ups || [];
    var out = '';
    ups.forEach(function (up) {
      out += '<a href="#" class="' + cls + (state.tab === 'up' ? ' selected' : '') +
        '" data-tab="up">' + esc(up.name) + (cls === 'dtab' ? '<span></span>' : '') + '</a>';
    });
    // 后续 UP 主待填充占位
    var slots = Math.max(3, 4 - ups.length);
    for (var i = ups.length; i < ups.length + slots; i++) {
      out += '<a href="#" class="' + cls + '" data-tab="pending">UP' + (i + 1) +
        ' 待填充' + (cls === 'dtab' ? '<span></span>' : '') + '</a>';
    }
    return out;
  }

  // 各数据源的榜单 tab（首页胶囊只放 B站UP主；详情页 tabs 放各站榜单）
  var SOURCE_TABS = [
    ['xifan_danmaku', '弹幕榜', 'https://next.xifanacg.com/rankings?kind=danmaku_heat'],
    ['xifan_weekly', '周热榜', 'https://next.xifanacg.com/rankings?kind=trending_week'],
    ['xifan_weekly_ongoing', '新番榜', 'https://next.xifanacg.com/rankings?kind=trending_week'],
  ];
  function sourceTabHTML(cls) {
    var out = '';
    SOURCE_TABS.forEach(function (t) {
      out += '<a href="#/rank/' + t[0] + '" class="' + cls +
        (state.tab === t[0] ? ' selected' : '') + '" data-tab="' + t[0] + '">' +
        esc(t[1]) + (cls === 'dtab' ? '<span></span>' : '') + '</a>';
    });
    return out;
  }

  function renderUpTabs() {
    // 首页胶囊只放 B站UP主；稀饭等外部榜单放详情页 tabs
    $('#home-board-tabs').innerHTML = upTabHTML('btab');
    $('#detail-tabs').innerHTML = upTabHTML('dtab') + sourceTabHTML('dtab');
  }

  function prevSeason(s) {
    var m = /^(\d{4})Q([1-4])$/.exec(s || '');
    if (!m) return null;
    var y = parseInt(m[1], 10), q = parseInt(m[2], 10);
    return q === 1 ? (y - 1) + 'Q4' : y + 'Q' + (q - 1);
  }

  function renderSeasons() {
    // 不硬编码：当前季度 + 上季度，真实季度来自数据
    var cur = state.data.meta.current_season;
    var seasons = [cur, prevSeason(cur)].filter(Boolean);
    $('#season-chips').innerHTML = seasons.map(function (s) {
      return '<a href="#" class="season-chip' + (s === state.season ? ' selected' : '') +
        '" data-season="' + esc(s) + '">' + esc(s) + '</a>';
    }).join('');
    $$('.season-chip').forEach(function (chip) {
      chip.addEventListener('click', function (ev) {
        ev.preventDefault();
        // 单选；再点已选中的则取消，显示所有季度
        state.season = state.season === chip.dataset.season ? null : chip.dataset.season;
        state.detailCache = {}; state.prefetched = {};
        renderSeasons(); renderHome();
      });
    });
  }

  /* ---------------- 路由：hash 软页面 ---------------- */
  function parseHash() {
    var h = (location.hash || '#/').replace(/^#/, '');
    if (h.indexOf('/rank/') === 0) {
      var parts = h.split('/');
      return { view: 'detail', tab: parts[2] || 'up' };
    }
    return { view: 'home' };
  }

  function applyRoute() {
    var r = parseHash();
    if (r.tab) state.tab = r.tab;
    var showDetail = r.view === 'detail';
    $('#view-home').classList.toggle('active', !showDetail);
    $('#view-detail').classList.toggle('active', showDetail);
    $$('.dtab').forEach(function (t) { t.classList.toggle('selected', t.dataset.tab === state.tab); });
    $$('.btab').forEach(function (t) { t.classList.toggle('selected', t.dataset.tab === state.tab); });
    if (showDetail) renderDetail(0);
  }

  function bindTabs() {
    $$('.dtab, .btab').forEach(function (t) {
      t.addEventListener('click', function (e) {
        e.preventDefault();
        state.tab = t.dataset.tab || 'up';
        state.detailCache = {}; state.prefetched = {};
        $$('.dtab, .btab').forEach(function (x) {
          x.classList.toggle('selected', x.dataset.tab === state.tab);
        });
        if ($('#view-detail').classList.contains('active')) renderDetail(0);
        else renderHome();
      });
    });
    $$('[data-back]').forEach(function (b) {
      b.addEventListener('click', function (ev) { ev.preventDefault(); history.back(); });
    });
    $$('.card').forEach(function () {});
  }

  function bindDetailScroll() {
    var scroller = $('#detail-scroll'), header = $('#compact-header');
    if (!scroller || !header) return;
    scroller.addEventListener('scroll', function () {
      header.classList.toggle('show', scroller.scrollTop > 110);
    });
  }

  function bindInfo() {
    var btn = $('#rate-info'), pop = $('#info-popover'), mask = $('#popover-mask');
    if (!btn || !pop || !mask) return;
    function close() { pop.classList.remove('show'); mask.classList.remove('show'); }
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (pop.classList.contains('show')) close();
      else { pop.classList.add('show'); mask.classList.add('show'); }
    });
    mask.addEventListener('click', close);
  }

  /* ---------------- 启动 ---------------- */
  window.__rankImgErr = function (img, idx) {
    var list = currentList();
    if (list[idx]) onImgError(img, list[idx]);
  };
  window.__rankDetailImgErr = function (img, idx) {
    var list = currentList();
    if (list[idx]) onImgError(img, list[idx]);
  };

  function boot(data) {
    state.data = data;
    window.__rankDebug = function () {
      return { prefetched: Object.keys(state.prefetched).length,
               listLen: currentList().length, season: state.season, tab: state.tab };
    };
    renderSeasons();
    renderUpTabs();
    renderHome();
    bindTabs();
    bindInfo();
    bindDetailScroll();
    applyRoute();
    window.addEventListener('hashchange', applyRoute);
  }

  fetch(DATA_URL, { cache: 'no-store' })
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(boot)
    .catch(function (err) {
      $('#cards-hot').innerHTML = '<div style="padding:24px 16px;color:#9499a0">数据加载失败：' + esc(err.message) + '</div>';
      console.error(err);
    });
})();
