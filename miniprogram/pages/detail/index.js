const api = require("../../utils/api");
const favorites = require("../../utils/favorites");

Page({
  data: {
    id: "",
    isFav: false,
    recipe: {
      title: "",
      cover_image: "",
      min_age_month: 0,
      tags: [],
      difficulty: 1,
      time_cost: 0,
      nutrition_tip: "",
      ingredients: [],
      steps: [],
      warnings: [],
    },
  },

  async onLoad(options) {
    const id = options && options.id ? decodeURIComponent(options.id) : "";
    this.setData({ id, isFav: favorites.isFavorite(id) });
    await this.loadRecipe();
  },

  onShow() {
    wx.setKeepScreenOn({ keepScreenOn: true });
  },

  onHide() {
    wx.setKeepScreenOn({ keepScreenOn: false });
  },

  onUnload() {
    wx.setKeepScreenOn({ keepScreenOn: false });
  },

  async loadRecipe() {
    wx.showLoading({ title: "加载中" });
    try {
      const manifest = await api.fetchManifest();
      const recipe = await api.fetchRecipe(this.data.id, { version: manifest && manifest.version });
      if (recipe) {
        this.setData({ recipe });
      } else {
        wx.showToast({ title: "未找到食谱", icon: "error" });
      }
    } finally {
      wx.hideLoading();
    }
  },

  onToggleFav() {
    const { isFavorite } = favorites.toggleFavorite(this.data.id);
    this.setData({ isFav: isFavorite });
  },

  onShareAppMessage() {
    const title = this.data.recipe && this.data.recipe.title ? this.data.recipe.title : "宝宝辅食";
    return {
      title,
      path: `/pages/detail/index?id=${encodeURIComponent(this.data.id)}`,
    };
  },
});
