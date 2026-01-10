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

function setEquals(a, b) {
  if (a.size !== b.size) return false;
  for (const v of a) {
    if (!b.has(v)) return false;
  }
  return true;
}

function buildMealTagOptions(items) {
  const has = new Set();
  const lunchIds = new Set();
  const dinnerIds = new Set();

  (items || []).forEach((it) => {
    if (!it || !Array.isArray(it.tags)) return;
    it.tags.forEach((t) => has.add(t));
    if (it.tags.includes("午餐")) lunchIds.add(it.id);
    if (it.tags.includes("晚餐")) dinnerIds.add(it.id);
  });

  const options = [];
  if (has.has("早餐")) options.push("早餐");

  const lunchDinnerIdentical = lunchIds.size > 0 && setEquals(lunchIds, dinnerIds);
  if (!lunchDinnerIdentical && (has.has("午餐") || has.has("晚餐"))) {
    if (has.has("午餐")) options.push("午餐");
    if (has.has("晚餐")) options.push("晚餐");
  } else if (has.has("正餐") || lunchDinnerIdentical) {
    options.push("正餐");
  }

  if (has.has("小吃")) options.push("小吃");
  return options.length ? options : ["早餐", "午餐", "晚餐", "小吃"];
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
  const start = 0; // consistent start
  const end = Math.max(0, page) * Math.max(1, pageSize);
  return items.slice(start, end);
}

Page({
  data: {
    query: "",
    bucket: "",
    activeTag: "",
    tagOptions: [],
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
      // Randomize the order
      const shuffled = this.shuffle(items);
      this.setData({ indexItems: shuffled, tagOptions: buildMealTagOptions(shuffled) });
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
    this.applyFilters();
  },

  onTagTap(e) {
    const tag = e.currentTarget.dataset.tag;
    const shuffled = this.shuffle(this.data.indexItems || []);
    this.setData({ activeTag: tag || "", indexItems: shuffled }, () => this.applyFilters());
  },

  onClear() {
    const shuffled = this.shuffle(this.data.indexItems || []);
    this.setData({ query: "", activeTag: "", bucket: "", indexItems: shuffled }, () => this.applyFilters());
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

    if (tag) {
      if (tag === "正餐") {
        items = items.filter((x) => {
          const tags = x && x.tags;
          if (!Array.isArray(tags)) return false;
          if (tags.includes("正餐")) return true;
          return tags.includes("午餐") && tags.includes("晚餐");
        });
      } else {
        items = items.filter((x) => Array.isArray(x.tags) && x.tags.includes(tag));
      }
    }

    if (q) {
      items = items.filter((x) => {
        const title = (x.title || "").toLowerCase();
        const tags = (x.tags || []).join(" ").toLowerCase();
        // Check title or tags using fuzzy match
        return fuzzyMatch(title, q) || fuzzyMatch(tags, q);
      });
    }

    this.setData({ filteredAll: items, page: 1 });
    this.updateDisplayed();
  },

  onOpenDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/detail/index?id=${encodeURIComponent(id)}` });
  },

  shuffle(array) {
    const arr = array.slice();
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  },
});
