const api = require("../../utils/api");

function splitColumns(items) {
  const left = [];
  const right = [];
  items.forEach((x, idx) => {
    if (idx % 2 === 0) left.push(x);
    else right.push(x);
  });
  return { left, right };
}

function paginate(items, page, pageSize) {
  const end = Math.max(0, page) * Math.max(1, pageSize);
  return items.slice(0, end);
}

Page({
  data: {
    query: "",
    bucket: "",
    activeTag: "",
    tagOptions: ["早餐", "正餐", "点心"],
    indexItems: [],
    filteredAll: [],
    filtered: [],
    left: [],
    right: [],
    totalCount: 0,
    page: 1,
    pageSize: 10,
    hasMore: false,
    loadingMore: false,
  },

  async onLoad(options) {
    const query = options && options.q ? decodeURIComponent(options.q) : "";
    const bucket = options && options.bucket ? decodeURIComponent(options.bucket) : "";
    
    if (bucket) {
      wx.setNavigationBarTitle({ title: `${bucket} 辅食` });
    } else if (query) {
      wx.setNavigationBarTitle({ title: `搜索: ${query}` });
    }

    this.setData({ query, bucket });

    wx.showLoading({ title: "加载中" });
    try {
      const index = await api.fetchIndex();
      const items = (index && index.items) || [];
      this.setData({ indexItems: items });
      this.applyFilters();
    } finally {
      wx.hideLoading();
    }
  },

  onReachBottom() {
    if (!this.data.hasMore || this.data.loadingMore) return;
    this.setData({ loadingMore: true });
    const nextPage = (this.data.page || 1) + 1;
    this.setData({ page: nextPage });
    this.updateDisplayed();
    this.setData({ loadingMore: false });
  },

  onQueryInput(e) {
    this.setData({ query: (e.detail && e.detail.value) || "" });
  },

  onTagTap(e) {
    const tag = e.currentTarget.dataset.tag;
    this.setData({ activeTag: tag || "" });
    this.applyFilters();
  },

  onClear() {
    this.setData({ query: "", activeTag: "", bucket: "" });
    this.applyFilters();
  },

  updateDisplayed() {
    const page = this.data.page || 1;
    const pageSize = this.data.pageSize || 10;
    const all = this.data.filteredAll || [];
    const shown = paginate(all, page, pageSize);
    const { left, right } = splitColumns(shown);
    this.setData({
      filtered: shown,
      left,
      right,
      totalCount: all.length,
      hasMore: shown.length < all.length,
    });
  },

  applyFilters() {
    const q = (this.data.query || "").trim().toLowerCase();
    const tag = this.data.activeTag || "";
    const bucket = this.data.bucket || "";

    let items = this.data.indexItems.slice();

    if (bucket) {
      // min_age_month 表示“最小可吃月龄”，因此按月龄导航时应筛选 <= 当前阶段上限（更符合喂养直觉）
      if (bucket === "4-6") items = items.filter((x) => x.min_age_month <= 6);
      else if (bucket === "6-8") items = items.filter((x) => x.min_age_month <= 8);
      else if (bucket === "8-12") items = items.filter((x) => x.min_age_month <= 12);
      else if (bucket === "1+") items = items.filter((x) => x.min_age_month >= 12 && x.min_age_month < 24);
      else if (bucket === "2+") items = items.filter((x) => x.min_age_month >= 24);
    }

    if (tag) items = items.filter((x) => Array.isArray(x.tags) && x.tags.includes(tag));

    if (q) {
      items = items.filter((x) => {
        const title = (x.title || "").toLowerCase();
        const tags = (x.tags || []).join(" ").toLowerCase();
        return title.includes(q) || tags.includes(q);
      });
    }

    this.setData({ filteredAll: items, page: 1 });
    this.updateDisplayed();
  },

  onOpenDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/detail/index?id=${encodeURIComponent(id)}` });
  },
});
