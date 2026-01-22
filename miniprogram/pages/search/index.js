const api = require("../../utils/api");
const storage = require("../../utils/storage");
const { STORAGE_KEYS } = require("../../config");

const HISTORY_LIMIT = 20;

function normalizeHistory(list) {
  if (!Array.isArray(list)) return [];
  return list
    .map((x) => String(x || "").trim())
    .filter((x) => x);
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

function paginate(items, page, pageSize) {
  const start = 0;
  const end = Math.max(0, page) * Math.max(1, pageSize);
  return items.slice(start, end);
}

Page({
  data: {
    query: "",
    history: [],
    resultsAll: [],
    results: [],
    searched: false,
    indexItems: [],
    totalCount: 0,
    page: 1,
    pageSize: 10,
    hasMore: false,
    loadingMore: false,
  },

  async onLoad(options) {
    const history = normalizeHistory(storage.get(STORAGE_KEYS.searchHistory, []));
    const query = options && options.q ? decodeURIComponent(options.q) : "";
    this.setData({ history, query });
    if (query) await this.doSearch(query);
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
    this.setData({ indexItems: items });
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
        this.updateDisplayed();
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

  onReachBottom() {
    if (!this.data.hasMore || this.data.loadingMore) return;
    this.setData({ loadingMore: true });
    const nextPage = (this.data.page || 1) + 1;
    this.setData({ page: nextPage });
    this.updateDisplayed();
    this.setData({ loadingMore: false });
  },

  updateDisplayed() {
    const page = this.data.page || 1;
    const pageSize = this.data.pageSize || 10;
    const all = this.data.resultsAll || [];
    const shown = paginate(all, page, pageSize);
    this.setData({
      results: shown,
      totalCount: all.length,
      hasMore: shown.length < all.length,
    });
  },
});
