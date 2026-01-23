const api = require("../../utils/api");
const storage = require("../../utils/storage");
const { STORAGE_KEYS, DEFAULT_COVER } = require("../../config");

const app = getApp();
const HISTORY_LIMIT = 20;
const HOT_KEYWORDS_LIMIT = 4;
const RECOMMEND_LIMIT = 16;

const HIGHLIGHT_STYLE = "color: #F97316; font-weight: 700;";

function normalizeHistory(list) {
  if (!Array.isArray(list)) return [];
  return list
    .map((x) => String(x || "").trim())
    .filter((x) => x);
}

function shuffleInPlace(list) {
  for (let i = list.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [list[i], list[j]] = [list[j], list[i]];
  }
  return list;
}

function fuzzyMatch(text, query) {
  if (!query) return true;
  text = text.toLowerCase();
  query = query.toLowerCase();
  let i = 0, j = 0;
  while (i < text.length && j < query.length) {
    if (text[i] === query[j]) {
      j++;
    }
    i++;
  }
  return j === query.length;
}

function buildHighlightNodes(text, query) {
  const content = String(text || "");
  const needle = String(query || "").trim();
  if (!needle) return [{ type: "text", text: content }];
  const lowerText = content.toLowerCase();
  const lowerNeedle = needle.toLowerCase();
  if (!lowerNeedle) return [{ type: "text", text: content }];
  const nodes = [];
  let idx = 0;
  while (idx < content.length) {
    const matchIndex = lowerText.indexOf(lowerNeedle, idx);
    if (matchIndex === -1) break;
    if (matchIndex > idx) {
      nodes.push({ type: "text", text: content.slice(idx, matchIndex) });
    }
    nodes.push({
      name: "span",
      attrs: { style: HIGHLIGHT_STYLE },
      children: [{ type: "text", text: content.slice(matchIndex, matchIndex + lowerNeedle.length) }],
    });
    idx = matchIndex + lowerNeedle.length;
  }
  if (idx < content.length) {
    nodes.push({ type: "text", text: content.slice(idx) });
  }
  return nodes.length ? nodes : [{ type: "text", text: content }];
}

function decorateItem(item, query) {
  const title = String(item && item.title ? item.title : "");
  const tags = Array.isArray(item && item.tags) ? item.tags : [];
  return {
    ...item,
    titleNodes: buildHighlightNodes(title, query),
    tagNodes: tags.map((tag) => buildHighlightNodes(tag, query)),
  };
}

function pickHotKeywords(items, limit) {
  const countMap = new Map();
  (items || []).forEach((item) => {
    const tags = Array.isArray(item && item.tags) ? item.tags : [];
    tags.forEach((tag) => {
      const key = String(tag || "").trim();
      if (!key) return;
      countMap.set(key, (countMap.get(key) || 0) + 1);
    });
  });
  const entries = Array.from(countMap.entries()).sort((a, b) => b[1] - a[1]);
  const poolSize = Math.max(limit * 5, limit);
  const pool = entries.slice(0, poolSize).map(([key]) => key);
  shuffleInPlace(pool);
  return pool.slice(0, limit);
}

function pickRecommendations(items, limit) {
  const pool = (items || []).filter((item) => item && item.id && item.title && item.cover_image);
  shuffleInPlace(pool);
  return pool.slice(0, limit);
}

function buildRecommendColumns(items, limit) {
  const recommendations = pickRecommendations(items, limit);
  return splitColumns(recommendations);
}

function splitColumns(items) {
  const left = [];
  const right = [];
  (items || []).forEach((item, index) => {
    if (index % 2 === 0) left.push(item);
    else right.push(item);
  });
  return { left, right };
}

function paginate(items, page, pageSize) {
  const start = 0;
  const end = Math.max(0, page) * Math.max(1, pageSize);
  return items.slice(start, end);
}

Page({
  data: {
    navHeight: app.globalData.navHeight,
    navCapsuleTop: app.globalData.navCapsuleTop,
    navCapsuleHeight: app.globalData.navCapsuleHeight,
    query: "",
    history: [],
    hotKeywords: [],
    recommendLeft: [],
    recommendRight: [],
    resultsAll: [],
    results: [],
    searched: false,
    indexItems: [],
    totalCount: 0,
    page: 1,
    pageSize: 10,
    hasMore: false,
    loadingMore: false,
    defaultCover: DEFAULT_COVER,
  },

  async onLoad(options) {
    this.setData({ navMarginBottom: app.globalData.navMarginBottom });

    const history = normalizeHistory(storage.get(STORAGE_KEYS.searchHistory, []));
    const query = options && options.q ? decodeURIComponent(options.q) : "";
    this.setData({ history, query });
    if (query) await this.doSearch(query);
  },

  onBack() {
    wx.navigateBack({ delta: 1 });
  },

  onQueryInput(e) {
    this.setData({ query: (e.detail && e.detail.value) || "" });
  },

  onSearch() {
    this.doSearch();
  },

  onClearQuery() {
    this.setData({
      query: "",
      resultsAll: [],
      results: [],
      searched: false,
      totalCount: 0,
      page: 1,
      hasMore: false,
      loadingMore: false,
    });
  },

  async ensureIndexItems() {
    if (this.data.indexItems && this.data.indexItems.length) return this.data.indexItems;
    const index = await api.fetchIndex();
    const items = (index && index.items) || [];
    const hotKeywords = this.data.hotKeywords && this.data.hotKeywords.length
      ? this.data.hotKeywords
      : pickHotKeywords(items, HOT_KEYWORDS_LIMIT);
    const { left: recommendLeft, right: recommendRight } = buildRecommendColumns(items, RECOMMEND_LIMIT);
    this.setData({ indexItems: items, hotKeywords, recommendLeft, recommendRight });
    return items;
  },

  addHistory(query) {
    const text = String(query || "").trim();
    if (!text) return;
    const history = this.data.history || [];
    const next = [text, ...history.filter((x) => x !== text)].slice(0, HISTORY_LIMIT);
    this.setData({ history: next });
    storage.set(STORAGE_KEYS.searchHistory, next);
  },

  async doSearch(overrideQuery) {
    const nextQuery = overrideQuery !== undefined ? String(overrideQuery) : this.data.query;
    const query = String(nextQuery || "").trim();
    if (!query) {
      this.setData({
        resultsAll: [],
        results: [],
        searched: false,
        query,
        totalCount: 0,
        page: 1,
        hasMore: false,
        loadingMore: false,
      });
      return;
    }
    if (query !== this.data.query) this.setData({ query });
    this.addHistory(query);
    wx.showLoading({ title: "搜索中" });
    try {
      const items = await this.ensureIndexItems();
      const resultsAll = items.filter((x) => {
        const title = (x.title || "").toLowerCase();
        const tags = (x.tags || []).join(" ").toLowerCase();
        return fuzzyMatch(title, query) || fuzzyMatch(tags, query);
      });
      this.setData({ resultsAll, searched: true, totalCount: resultsAll.length, page: 1 }, () => {
        this.updateDisplayed(query);
      });
    } finally {
      wx.hideLoading();
    }
  },

  onTapHistory(e) {
    const query = e.currentTarget.dataset.query;
    this.doSearch(query);
  },

  onClearHistory() {
    storage.remove(STORAGE_KEYS.searchHistory);
    this.setData({ history: [] });
  },

  onOpenDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/detail/index?id=${encodeURIComponent(id)}` });
  },

  onCoverError(e) {
    const id = e.currentTarget.dataset.id;
    const section = e.currentTarget.dataset.section;
    if (!id) return;
    const fallback = this.data.defaultCover;
    const updateList = (list) => (list || []).map((item) =>
      item && item.id === id ? { ...item, cover_image: fallback } : item,
    );

    if (section === "results") {
      this.setData({
        resultsAll: updateList(this.data.resultsAll),
        results: updateList(this.data.results),
      });
      return;
    }

    this.setData({
      recommendLeft: updateList(this.data.recommendLeft),
      recommendRight: updateList(this.data.recommendRight),
    });
  },

  async onRefreshRecommend() {
    const items = this.data.indexItems && this.data.indexItems.length
      ? this.data.indexItems
      : await this.ensureIndexItems();
    const { left: recommendLeft, right: recommendRight } = buildRecommendColumns(items, RECOMMEND_LIMIT);
    this.setData({ recommendLeft, recommendRight });
  },

  onReachBottom() {
    if (!this.data.hasMore || this.data.loadingMore) return;
    this.setData({ loadingMore: true });
    const nextPage = (this.data.page || 1) + 1;
    this.setData({ page: nextPage });
    this.updateDisplayed();
    this.setData({ loadingMore: false });
  },

  updateDisplayed(overrideQuery) {
    const query = overrideQuery !== undefined ? String(overrideQuery) : this.data.query;
    const page = this.data.page || 1;
    const pageSize = this.data.pageSize || 10;
    const all = this.data.resultsAll || [];
    const shown = paginate(all, page, pageSize).map((item) => decorateItem(item, query));
    this.setData({
      results: shown,
      totalCount: all.length,
      hasMore: shown.length < all.length,
    });
  },
});
