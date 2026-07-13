# Auto-LifeOS Public Demo

Auto-LifeOS 是一个可公开访问的 LangGraph 饮食与家庭库存 Agent 演示。它展示从自然语言需求、结构化计划、两阶段确认，到 SQLite 事务扣减与撤销的完整路径。

## 公开演示边界

- 强制使用 Mock Provider，不连接外部模型，不需要任何 API 凭据。
- 所有用户、库存、知识库与 A/B 数据均为 synthetic/sample。
- 每个 Streamlit 浏览会话使用独立的临时 SQLite 数据库；新会话恢复相同基线。
- 数据只用于软件演示，服务重启后可以重置，不构成医疗建议。
- 项目不包含真实用户数据、本地数据库、求职资料或主项目 Git 历史。

## 功能

- 智能饮食推荐与 Pydantic 结构化计划
- 库存、过敏原、过期、单位与营养范围的确定性校验
- 第一次方案确认、实际用量修改、第二次执行确认
- 原子库存扣减、前后对比与当前会话撤销
- TF-IDF 私域知识检索
- 可读的 LangGraph Agent 执行轨迹
- 20 个合成案例的 Prompt 对比实验
- 会话隔离、架构与安全说明

## 本地运行

需要 Python 3.11。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m streamlit run app.py
```

Windows PowerShell 激活命令为 `.venv\\Scripts\\Activate.ps1`。

## 测试

```bash
pip install pytest
python -m pytest -q
```

测试覆盖双会话数据库隔离、跨会话扣减/撤销、新会话基线、两阶段确认、Mock 强制模式、凭据读取与可移植路径。

## 部署

Streamlit Community Cloud 配置：

- Repository：`auto-lifeos-demo`
- Branch：`main`
- Main file path：`app.py`
- Python：`3.11`
- Secrets：留空

详细步骤与验收项见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## License

MIT License。演示中的一般饮食信息不构成医疗建议。

