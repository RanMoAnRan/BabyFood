Component({
  data: {
    selected: 0,
    list: [
      { pagePath: "/pages/home/index", text: "首页" },
      { pagePath: "/pages/profile/index", text: "我的" },
    ],
  },

  methods: {
    setSelected(index) {
      this.setData({ selected: Number(index) || 0 });
    },

    onTap(e) {
      const index = Number(e.currentTarget.dataset.index) || 0;
      const item = this.data.list[index];
      if (!item || !item.pagePath) return;
      wx.switchTab({ url: item.pagePath });
      this.setSelected(index);
    },
  },
});

