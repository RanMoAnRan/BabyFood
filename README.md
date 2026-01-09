# BabyFood MiniApp

一个“静态数据 + CDN + 离线缓存”的微信小程序骨架，用于宝宝辅食查阅（无登录、零服务器）。

## 目录结构

- `miniprogram/`：微信小程序代码
- `backend/`：后端/数据构建（抓取、清洗、图片处理）
- `backend/daily_job.py`：每日数据更新脚本（单站适配快速上线）
- `backend/data/`：静态数据产物（`manifest.json`、`recipes_index.json`、`recipes/{id}.json`、`images/`）
- `.github/workflows/daily.yml`：GitHub Actions 定时更新与自动提交

## 本地开发

1. 用微信开发者工具导入项目（根目录），`miniprogram/` 为小程序目录。
2. 本地联调（方案A）：
   - 生成数据：`.venv/bin/python3 backend/daily_job.py --limit 20 --no-images`
   - 启动静态服务：`python3 -m http.server 8000`
   - `miniprogram/config.js` 默认已指向：`http://127.0.0.1:8000/backend/data`
3. 远程/上线（方案B）：
   - 修改 `miniprogram/config.js` 里的 `CDN_BASE` 为你的 jsDelivr 地址（指向 `backend/data/`）。
3. 运行小程序：首次会优先拉取 `manifest.json`，失败则回退到 `miniprogram/seed/` 内置种子数据。

## 生成数据（本地）

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python3 backend/daily_job.py --dry-run --limit 1
# 加 --verbose 可打印抓取进度/失败原因
```

落盘写入（会写 `backend/data/` 与 `backend/data/images/`）：

```bash
.venv/bin/python3 backend/daily_job.py --limit 20
```

### 重新初始化数据（可选）

脚本不会自动清理旧数据；如果想从零重新生成，可以先删除产物目录：

```bash
rm -rf backend/data/recipes backend/data/images
rm -f backend/data/manifest.json backend/data/recipes_index.json

.venv/bin/python3 backend/daily_job.py --site all --verbose
```

不想重新下图可不要删 `backend/data/images`（或运行时加 `--no-images`）；不想翻译可加 `--no-translate`。

## 数据协议（推荐）

小程序启动只拉很小的 `manifest.json`，再按需拉取列表索引与详情，避免单个超大 JSON：

- `manifest.json`：版本与分片信息（更新入口）
- `recipes_index.json`：列表页用的轻字段
- `recipes/{id}.json`：详情页完整字段（步骤/食材/警示等）

## 自动化更新

GitHub Actions 会按计划执行 `backend/daily_job.py`，生成/更新 `data/` 下的 JSON 与图片，并在有变更时自动提交到仓库。

### 默认数据源（单站快速上线）

当前 `backend/daily_job.py` 默认会聚合多个站点（均为 USDA 体系内站点），仍建议保留溯源字段并抽样核对可再分发范围：

- `Nutrition.gov (USDA)`
  - 抓取入口：`https://www.nutrition.gov/recipes/search`
  - 解析方式：优先解析页面内的 `schema.org Recipe (JSON-LD)` + Ingredients/Steps 的结构化 HTML
  - 数据字段：会写入 `source_url`（Nutrition.gov 页面）与 `origin_url`（如页面提供外链来源）
- `MyPlate Kitchen (USDA)`
  - 抓取入口：`https://www.myplate.gov/myplate-kitchen/recipes`
  - 解析方式：优先解析页面内的 `schema.org Recipe (JSON-LD)`；列表页优先用 sitemap 兜底获取 URL
  - 数据字段：会写入 `source_url` 与 `origin_url`（若页面提供）

> 注意：即便是公共站点，也可能存在第三方图片/内容的例外；上线前建议抽样核对并保留溯源链接。
