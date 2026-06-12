# 2026 世界杯 · 赛事通

世界欠2026年世界杯网页版应用，支持实況比分、赛程、淘汰赛对阵和 Polymarket 预测赔率。

## 数据源

- **赛程 & 分组**: FIFA 官网
- **比赛比分**: FIFA.com（通过定时抓取）
- **预测赔率**: [Polymarket](https://polymarket.com) CLOB API

## 部署到 GitHub Pages

```bash
# 1. 在 GitHub 上创建新仓库（不要初始化 README/LICENSE）

# 2. 推送到 GitHub
git remote add origin https://github.com/你的用户名/wc-2026.git
git branch -M main
git push -u origin main

# 3. 去仓库 Settings → Pages
#    选择 "Deploy from a branch" → main → / (root)
#    访问 https://你的用户名.github.io/wc-2026/
```

部署后，GitHub Actions 每 30 分钟自动抓取最新比赛结果和 Polymarket 赔率。
