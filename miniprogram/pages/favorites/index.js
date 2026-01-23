const api = require("../../utils/api");
const favorites = require("../../utils/favorites");
const { DEFAULT_COVER } = require("../../config");

const app = getApp();

Page({
  data: {
    navHeight: app.globalData.navHeight,
    navCapsuleTop: app.globalData.navCapsuleTop,
    navCapsuleHeight: app.globalData.navCapsuleHeight,
    favItems: [],
    allSelected: false,
    selectedCount: 0,
    defaultCover: DEFAULT_COVER,
  },

  onLoad() {
    this.setData({ navMarginBottom: app.globalData.navMarginBottom });
    this.loadFavorites();
  },

  onShow() {
    if (this.getTabBar && this.getTabBar()) {
      this.getTabBar().setSelected(2);
    }
    this.loadFavorites();
  },

  async onPullDownRefresh() {
    await this.loadFavorites();
    wx.stopPullDownRefresh();
  },

  async loadFavorites() {
    const ids = favorites.getFavorites();
    if (ids.length === 0) {
      this.setData({ favItems: [], selectedCount: 0, allSelected: false });
      return;
    }
    const selectedSet = new Set(
      (this.data.favItems || []).filter((x) => x && x.selected).map((x) => x.id),
    );
    const index = await api.fetchIndex();
    const items = (index && index.items) || [];
    const map = new Map(items.map((x) => [x.id, x]));
    const favItems = ids
      .map((id) => map.get(id))
      .filter(Boolean)
      .map((item) => ({ ...item, selected: selectedSet.has(item.id) }));
    this.setData({ favItems }, () => this.updateSelectionState());
  },

  onOpenDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/detail/index?id=${encodeURIComponent(id)}` });
  },

  onRemoveFav(e) {
    const id = e.currentTarget.dataset.id;
    favorites.removeFavorite(id);
    this.loadFavorites();
  },

  onCoverError(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;
    const fallback = this.data.defaultCover;
    const favItems = (this.data.favItems || []).map((item) =>
      item && item.id === id ? { ...item, cover_image: fallback } : item,
    );
    this.setData({ favItems });
  },

  onToggleSelect(e) {
    const id = e.currentTarget.dataset.id;
    const favItems = (this.data.favItems || []).map((item) => {
      if (!item || item.id !== id) return item;
      return { ...item, selected: !item.selected };
    });
    this.setData({ favItems }, () => this.updateSelectionState());
  },

  onToggleAll() {
    const target = !this.data.allSelected;
    const favItems = (this.data.favItems || []).map((item) =>
      item ? { ...item, selected: target } : item,
    );
    this.setData({ favItems }, () => this.updateSelectionState());
  },

  onGoSearch() {
    wx.navigateTo({ url: "/pages/search/index" });
  },

  onDeleteSelected() {
    const selected = (this.data.favItems || []).filter((x) => x && x.selected);
    if (selected.length === 0) return;
    wx.showModal({
      title: "删除收藏",
      content: `确认删除已选的 ${selected.length} 条收藏吗？`,
      confirmText: "删除",
      confirmColor: "#EF4444",
      success: (res) => {
        if (!res.confirm) return;
        favorites.removeFavorites(selected.map((x) => x.id));
        this.loadFavorites();
      },
    });
  },

  updateSelectionState() {
    const items = this.data.favItems || [];
    const selectedCount = items.filter((x) => x && x.selected).length;
    const allSelected = items.length > 0 && selectedCount === items.length;
    this.setData({ selectedCount, allSelected });
  },
});
