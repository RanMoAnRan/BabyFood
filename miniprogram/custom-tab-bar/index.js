Component({
  data: {
    selected: 0,
    list: [
      { pagePath: "/pages/home/index", text: "首页" },
      { pagePath: "/pages/profile/index", text: "我的" },
    ],
  },

  lifetimes: {
    attached() {
      this.syncSelectedWithRoute();
    },
  },

  pageLifetimes: {
    show() {
      this.syncSelectedWithRoute();
    },
  },

  methods: {
    setSelected(index) {
      const n = Number(index);
      this.setData({ selected: Number.isFinite(n) ? n : 0 });
    },

    syncSelectedWithRoute() {
      const pages = getCurrentPages();
      const current = pages && pages.length ? pages[pages.length - 1] : null;
      const route = (current && (current.route || current.__route__)) || "";
      if (!route) return;

      const normalizedRoute = route.replace(/^\//, "");
      const list = this.data.list || [];
      const index = list.findIndex((it) => String(it.pagePath || "").replace(/^\//, "") === normalizedRoute);
      if (index >= 0 && index !== this.data.selected) {
        this.setData({ selected: index });
      }
    },

    onTap(e) {
      const indexRaw = Number(e.currentTarget.dataset.index);
      const index = Number.isFinite(indexRaw) ? indexRaw : 0;
      const item = this.data.list[index];
      if (!item || !item.pagePath) return;
      wx.switchTab({ url: item.pagePath });
      this.setSelected(index);
    },
  },
});
