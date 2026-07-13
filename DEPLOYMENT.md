# Streamlit Community Cloud 部署说明

1. 将本目录作为独立仓库推送到 GitHub，默认分支为 `main`。
2. 在 Streamlit Community Cloud 新建 App，选择 `auto-lifeos-demo`。
3. 使用分支 `main`、入口 `app.py`、Python 3.11。
4. Secrets 保持为空并部署。
5. 构建完成后验证首页、计划生成、两次确认、扣减、撤销和新会话基线。

本项目不读取 API 凭据。运行数据保存在各浏览会话独立的临时 SQLite 文件中，不提交到 Git。

