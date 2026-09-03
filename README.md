# K8s Datagraph RCA

面向 Kubernetes 微服务故障的自主多 Agent 根因分析系统。通过 LangGraph 编排 **Triage → Planner → 并行 RCA Worker → Supervisor** 流水线，结合 Datagraph 集群拓扑与 MCP 可观测工具（Prometheus、Jaeger、Kubernetes API），自动完成故障检测、调查与根因定位。

## 仓库结构

```
k8s-datagraph-rca/
├── sre-agent/              # 多 Agent 系统核心实现（LangGraph）
│   ├── graph.py            # 父图调度与路由
│   ├── agents/             # Triage / Planner / RCA / Supervisor
│   ├── models/             # 状态定义与 Reducer
│   ├── tools/              # MCP 工具接入
│   ├── prompts/            # Agent 提示词
│   ├── config/             # 运行时配置
│   ├── evaluation/         # 检测 / 定位 / LLM-Judge 评测
│   └── experiments_runner/ # 实验编排与故障场景配置
└── registry/               # 本地镜像仓库脚本
```

## 系统架构

```
START → triage_agent → planner_agent → schedule_rca_tasks
     → rca_router → [并行 rca_agent] | supervisor_agent
     → supervisor_router → schedule_rca_tasks | END
```

### 核心组件

1. **Triage Agent（混合式）**
   - 结合确定性启发式（延迟、错误率、饱和度等黄金信号）与 LLM 推理，结构化输出集群症状，降低幻觉风险。

2. **Planner Agent（拓扑感知）**
   - 基于 Neo4j Datagraph 理解服务依赖与上下游关系，生成去重、带优先级的 RCA 任务列表。

3. **RCA Worker（并行执行）**
   - 采用分而治之策略，LangGraph `Send` API 并行派发多个 Worker，各自通过 MCP 工具调查日志、链路追踪与指标。

4. **Supervisor Agent（汇总与回环）**
   - 聚合 Worker 报告，输出最终根因分析；证据不足时可触发反馈回环，调度剩余任务继续调查。

### 关键特性

- **Datagraph**：以图结构表达集群拓扑，引导 Planner 聚焦相关资源，避免无效探索。
- **MCP 工具层**：标准化可观测数据访问，对原始数据进行预筛选，优化上下文窗口与 token 开销。
- **并行 RCA + 反馈回环**：`rca_analyses_list` 经 `merge_rca_analyses` 按 priority 去重归并，Supervisor 可决定是否继续调度。

## 技术栈

LangGraph · LangChain · MCP · Neo4j · Prometheus · Jaeger · Kubernetes API · LangSmith

## 代码浏览路径

| 关注点 | 入口文件 |
|--------|----------|
| 父图拓扑与调度 | `sre-agent/graph.py` |
| 并行 RCA 派发 | `sre-agent/graph.py` → `rca_router` |
| 全局状态定义 | `sre-agent/models/states.py` |
| 结果归并 Reducer | `sre-agent/models/reducers.py` |
| Triage 实现 | `sre-agent/agents/triage_agent.py` |
| Planner 实现 | `sre-agent/agents/planner_agent.py` |
| RCA Worker 实现 | `sre-agent/agents/rca_agent.py` |
| Supervisor 实现 | `sre-agent/agents/supervisor_agent.py` |
| 运行时配置 | `sre-agent/config/settings.py` |
| 评测逻辑 | `sre-agent/evaluation/evaluation.py` |

## 环境要求

- Python 3.13+
- Poetry
- Docker & Kind（Kubernetes in Docker）
- OpenAI API Key
- MCP 可观测服务（Prometheus / Jaeger 等，按需部署）

## 安装

```bash
git clone https://github.com/whrgg/k8s-datagraph-rca.git
cd k8s-datagraph-rca

poetry install

cp .env.example .env
# 编辑 .env，填入 API Key 与集群/MCP 连接信息
```

## 运行

**方式一：LangGraph Studio（推荐，可视化调试）**

```bash
cd sre-agent
poetry run langgraph dev
```

**方式二：单次实验**

```bash
poetry run python sre-agent/launch_experiment.py
```

**方式三：批量实验**

```bash
poetry run python sre-agent/automated_experiment.py
```

## 配置说明

主要环境变量见 `.env.example`：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MAX_TOOL_CALLS` | 单个 RCA Worker 工具调用预算 | 8 |
| `RCA_TASKS_PER_ITERATION` | 每轮并行 RCA 任务数 | 3 |
| `TRACE_SERVICE_STARTING_POINT` | 链路追踪起始服务 | frontend |
| `PROMETHEUS_SERVER_URL` | Prometheus 地址 | http://localhost:9090 |
| `JAEGER_URL` | Jaeger 地址 | http://localhost:16686 |
| `NEO4J_URI` | Datagraph Neo4j 连接 | bolt://localhost:7687 |

## 评测指标

- **Detection（检测）**：是否正确识别异常
- **Localization（定位）**：是否准确定位根因资源（Service / Pod）
- **RCA Score（根因评分）**：LLM-as-a-Judge 语义评分（1–5 分 + 理由）
