const api = require("../../utils/api");
const favorites = require("../../utils/favorites");
const storage = require("../../utils/storage");
const { DEFAULT_COVER, STORAGE_KEYS } = require("../../config");

const app = getApp();

Page({
  data: {
    navHeight: app.globalData.navHeight,
    navCapsuleTop: app.globalData.navCapsuleTop,
    navCapsuleHeight: app.globalData.navCapsuleHeight,
    id: "",
    isFav: false,
    defaultCover: DEFAULT_COVER,
    matchedAllergens: [],
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
    loading: true,
  },

  async onLoad(options) {
    this.setData({ navMarginBottom: app.globalData.navMarginBottom });

    const id = options && options.id ? decodeURIComponent(options.id) : "";
    this.setData({ id, isFav: favorites.isFavorite(id) });
    await this.loadRecipe();
  },

  onBack() {
    wx.navigateBack({ delta: 1 });
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
    // wx.showLoading({ title: "加载中" });
    this.setData({ loading: true });
    try {
      const manifest = await api.fetchManifest();
      const recipe = await api.fetchRecipe(this.data.id, { version: manifest && manifest.version });
      if (recipe) {
        this.checkAllergens(recipe);
        this.setData({ recipe });
      } else {
        wx.showToast({ title: "未找到辅食", icon: "error" });
      }
    } finally {
      // wx.hideLoading();
      this.setData({ loading: false });
    }
  },

  checkAllergens(recipe) {
    const profile = storage.get(STORAGE_KEYS.profile, {});
    const raw = profile && profile.allergens ? String(profile.allergens) : "";
    if (!raw) {
      this.setData({ matchedAllergens: [] });
      return;
    }
    const userAllergens = raw.split(/[,，、\s]+/).filter(Boolean);
    const matches = new Set();
    const ingredients = (recipe.ingredients || []).map((i) => i.name);

    userAllergens.forEach((allergen) => {
      ingredients.forEach((ing) => {
        // Simple containment check
        if (ing.includes(allergen) || allergen.includes(ing)) {
          matches.add(ing);
        }
      });
    });
    this.setData({ matchedAllergens: Array.from(matches) });
  },

  onToggleFav() {
    const { isFavorite } = favorites.toggleFavorite(this.data.id);
    this.setData({ isFav: isFavorite });
  },

  onHeroError() {
    this.setData({ "recipe.cover_image": this.data.defaultCover });
  },

  onStepImageError(e) {
    const index = Number(e.currentTarget.dataset.index);
    if (!Number.isFinite(index)) return;
    const steps = (this.data.recipe.steps || []).map((step, idx) =>
      idx === index ? { ...step, img: this.data.defaultCover } : step,
    );
    this.setData({ "recipe.steps": steps });
  },

  onShareAppMessage() {
    const title = this.data.recipe && this.data.recipe.title ? this.data.recipe.title : "宝宝辅食";
    return {
      title,
      path: `/pages/detail/index?id=${encodeURIComponent(this.data.id)}`,
    };
  },
});
