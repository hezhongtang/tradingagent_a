# TradingAgent_A 工作流图

> 从参数输入到报告输出的全流程树状图。每个环节已编号，可作为功能分支的切分点。

```
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 0: 预启动                                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [0.1] 加载 .env 环境变量                                            │
│    └─ API Keys: OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.            │
│    └─ 输出: os.environ 可用                                         │
│                                                                     │
│  [0.2] 检查自更新 (Windows PyInstaller only)                         │
│    └─ 读取 pyproject.toml 版本                                      │
│    └─ 请求 GitHub Releases API                                      │
│    └─ 有更新 → 用户确认 → 下载 → 替换 exe → 退出                     │
│    └─ 无更新 → 继续                                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 1: 用户参数采集 (交互式 CLI)                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [1.1] 显示欢迎界面 & 公告                                           │
│    └─ welcome.txt ASCII Art                                         │
│    └─ 远程公告拉取                                                   │
│                                                                     │
│  [1.2] 输入股票代码                                                  │
│    └─ 用户输入: 600519, 000001, ...                                │
│    └─ 校验: normalize_ticker_symbol() → 600519.SH                  │
│                                                                     │
│  [1.3] 输入分析日期                                                  │
│    └─ 用户输入: YYYY-MM-DD                                          │
│    └─ 校验: 有效日期 && 非未来                                       │
│                                                                     │
│  [1.4] 加载默认配置                                                  │
│    └─ build_runtime_config()                                        │
│    └─ 合并 DEFAULT_CONFIG + last_config.py                         │
│                                                                     │
│  [1.5] 配置确认 / 修改 (可选)                                         │
│    ├─ [1.5.1] 内部语言 (agent 间通信)                                 │
│    ├─ [1.5.2] 输出语言 (报告语言)                                     │
│    ├─ [1.5.3] 分析师团队 (多选: market/social/news/fundamentals)     │
│    ├─ [1.5.4] 研究深度 (浅=1 / 中=3 / 深=5 轮辩论)                    │
│    ├─ [1.5.5] LLM 提供商 + 后端 URL                                  │
│    ├─ [1.5.6] 快速思考模型 & 深度思考模型                              │
│    ├─ [1.5.7] 提供商调优 (reasoning_effort, thinking_level, ...)     │
│    └─ [1.5.8] 保存到 last_config.py                                 │
│                                                                     │
│  输出: selections dict                                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 2: 运行时配置 & 图初始化                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [2.1] 构建运行时配置                                                │
│    └─ 覆盖 max_debate_rounds, selected_analysts, LLM 设置等          │
│                                                                     │
│  [2.2] 创建 StatsCallbackHandler                                     │
│    └─ 跟踪: llm_calls, tool_calls, tokens_in, tokens_out            │
│                                                                     │
│  [2.3] 设置全局 dataflows 配置                                       │
│    └─ set_config() → 数据供应商路由                                  │
│                                                                     │
│  [2.4] 初始化 LLM 客户端 (工厂模式)                                    │
│    ├─ [2.4.1] Deep LLM 客户端 → 研究经理、投资组合经理                │
│    └─ [2.4.2] Quick LLM 客户端 → 分析师、交易员、辩论者                │
│                                                                     │
│  [2.5] 初始化 BM25 记忆系统 (5 个)                                    │
│    ├─ [2.5.1] Bull Memory                                           │
│    ├─ [2.5.2] Bear Memory                                           │
│    ├─ [2.5.3] Trader Memory                                         │
│    ├─ [2.5.4] Invest Judge Memory                                   │
│    └─ [2.5.5] Portfolio Manager Memory                              │
│                                                                     │
│  [2.6] 创建 ToolNode (4 组)                                          │
│    ├─ [2.6.1] Market Tools: get_stock_data, get_indicators          │
│    ├─ [2.6.2] Social Tools: get_news                                │
│    ├─ [2.6.3] News Tools: get_news, get_market_news,                │
│    │                     get_company_announcements                   │
│    └─ [2.6.4] Fundamentals Tools: get_fundamentals,                 │
│                                   get_balance_sheet,                │
│                                   get_cashflow,                     │
│                                   get_income_statement              │
│                                                                     │
│  [2.7] 创建 ConditionalLogic                                         │
│    └─ 辩论/风控轮次路由控制                                           │
│                                                                     │
│  [2.8] 构建 & 编译 LangGraph                                         │
│    └─ setup_graph(selected_analysts)                                │
│    └─ 动态添加分析师节点 + 固定团队节点 + 条件边                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 3: 多智能体图执行 (LangGraph Stream)                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [3.1] 创建初始 Agent 状态                                            │
│    └─ ticker, date, 空报告, 空辩论状态                                │
│                                                                     │
│  ─── 环节 A: 分析师团队 (顺序执行) ───                                 │
│                                                                     │
│  [3.2] 分析师链 (用户选择的顺序)                                       │
│    │                                                                │
│    ├─ [3.2.1] Market Analyst (市场分析师)                             │
│    │   ├─ 工具: get_stock_data → OHLCV 行情数据                       │
│    │   ├─ 工具: get_indicators → 技术指标                             │
│    │   └─ 输出: market_report                                       │
│    │                                                                │
│    ├─ [3.2.2] Social Analyst (舆情分析师)                             │
│    │   ├─ 工具: get_news → 社交媒体/论坛舆情                           │
│    │   └─ 输出: sentiment_report                                    │
│    │                                                                │
│    ├─ [3.2.3] News Analyst (新闻分析师)                               │
│    │   ├─ 工具: get_news → 新闻                                       │
│    │   ├─ 工具: get_market_news → 市场新闻                            │
│    │   ├─ 工具: get_company_announcements → 公司公告                   │
│    │   └─ 输出: news_report                                         │
│    │                                                                │
│    └─ [3.2.4] Fundamentals Analyst (基本面分析师)                     │
│        ├─ 工具: get_fundamentals → 财务指标                            │
│        ├─ 工具: get_balance_sheet → 资产负债表                        │
│        ├─ 工具: get_cashflow → 现金流量表                             │
│        ├─ 工具: get_income_statement → 利润表                         │
│        └─ 输出: fundamentals_report                                 │
│                                                                     │
│  ─── 环节 B: 研究团队辩论 ───                                          │
│                                                                     │
│  [3.3] Bull Researcher (看多研究员)                                    │
│    ├─ 输入: 4 份分析师报告 + 辩论历史 + bull_memory 检索              │
│    └─ 输出: 看多论点 → investment_debate_state                       │
│                                                                     │
│  [3.4] Bear Researcher (看空研究员)                                    │
│    ├─ 输入: 4 份分析师报告 + 辩论历史 + Bull 论点 + bear_memory 检索  │
│    └─ 输出: 看空反驳 → investment_debate_state                       │
│                                                                     │
│  [3.5] 辩论循环控制                                                   │
│    ├─ 条件: latest_speaker == Bull → 跳到 [3.4] Bear                 │
│    ├─ 条件: latest_speaker == Bear → 跳到 [3.3] Bull                 │
│    └─ 条件: count >= 2 * max_debate_rounds → 跳到 [3.6]             │
│                                                                     │
│  [3.6] Research Manager (研究经理)                                     │
│    ├─ 输入: 4 份分析师报告 + 完整辩论历史 + invest_judge_memory 检索  │
│    ├─ 评估辩论结果, 做出 Buy/Sell/Hold 决策                            │
│    └─ 输出: investment_plan (详细投资计划)                             │
│                                                                     │
│  ─── 环节 C: 交易员执行 ───                                            │
│                                                                     │
│  [3.7] Trader (交易员)                                                │
│    ├─ 输入: 4 份分析师报告 + investment_plan + trader_memory 检索     │
│    ├─ 考虑 A 股特性: T+1, 涨跌停, 流动性                               │
│    └─ 输出: trader_investment_plan (具体交易建议)                      │
│                                                                     │
│  ─── 环节 D: 风控辩论 (3 方轮换) ───                                   │
│                                                                     │
│  [3.8] Aggressive Analyst (激进风控)                                   │
│    ├─ 输入: 分析师报告 + 交易计划 + 辩论历史                            │
│    └─ 输出: 强调高收益机会 → risk_debate_state                       │
│                                                                     │
│  [3.9] Conservative Analyst (保守风控)                                 │
│    ├─ 输入: 以上全部 + Aggressive 论点                                │
│    └─ 输出: 强调下行风险/执行风险 → risk_debate_state                │
│                                                                     │
│  [3.10] Neutral Analyst (中性风控)                                     │
│    ├─ 输入: 以上全部 + Aggressive + Conservative 论点                 │
│    └─ 输出: 平衡观点(仓位/触发价/观察vs参与) → risk_debate_state      │
│                                                                     │
│  [3.11] 风控循环控制                                                  │
│    ├─ 条件: Aggressive → 跳到 [3.9] Conservative                     │
│    ├─ 条件: Conservative → 跳到 [3.10] Neutral                       │
│    ├─ 条件: Neutral → 跳回 [3.8] Aggressive (循环)                    │
│    └─ 条件: count >= 3 * max_risk_discuss_rounds → 跳到 [3.12]      │
│                                                                     │
│  ─── 环节 E: 最终决策 ───                                              │
│                                                                     │
│  [3.12] Portfolio Manager (投资组合经理)                               │
│    ├─ 输入: 分析师报告 + 交易计划 + 完整风控辩论 + portfolio_memory 检索│
│    └─ 输出: final_trade_decision (评级: Buy/Overweight/Hold/        │
│                                  Underweight/Sell)                   │
│                                                                     │
│  [3.13] Report Finalizer (报告定稿)                                    │
│    ├─ 将所有中间报告复制到 final_* 字段                                │
│    │   ├─ market_report → final_market_report                       │
│    │   ├─ sentiment_report → final_sentiment_report                 │
│    │   ├─ news_report → final_news_report                           │
│    │   ├─ fundamentals_report → final_fundamentals_report           │
│    │   ├─ investment_plan → final_investment_plan_report            │
│    │   ├─ trader_investment_plan → final_trader_investment_plan     │
│    │   └─ final_trade_decision → final_trade_decision_report        │
│    └─ 图执行结束 (END)                                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 4: CLI 流处理 & 实时展示                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [4.1] 逐块处理 Stream 输出                                           │
│    ├─ 分类消息类型 (Agent/Data/Control/User)                         │
│    ├─ 记录工具调用                                                     │
│    ├─ 更新分析师状态                                                  │
│    ├─ 跟踪辩论状态转换                                                │
│    └─ 更新 Rich Live 显示 (状态表 + 消息表 + 报告面板 + 页脚统计)      │
│                                                                     │
│  [4.2] 日志写入                                                     │
│    ├─ results/{ticker}/{date}/message_tool.log                      │
│    └─ results/{ticker}/{date}/reports/{section_name}.md             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 5: 后处理 & 输出                                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [5.1] 提取最终状态                                                   │
│    └─ final_state = trace[-1]                                       │
│                                                                     │
│  [5.2] 信号处理 (评级提取)                                            │
│    ├─ SignalProcessor 用 Quick LLM 从决策文本中提取单一评级词          │
│    └─ 输出: BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL            │
│                                                                     │
│  [5.3] 标记所有 Agent 完成                                            │
│                                                                     │
│  [5.4] 保存报告到磁盘 (用户确认)                                       │
│    ├─ {path}/1_analysts/                                           │
│    │   ├─ market_report.md                                          │
│    │   ├─ sentiment_report.md                                       │
│    │   ├─ news_report.md                                            │
│    │   └─ fundamentals_report.md                                    │
│    ├─ {path}/2_research/                                            │
│    │   └─ investment_plan.md                                        │
│    ├─ {path}/3_trading/                                             │
│    │   └─ trader_investment_plan_report.md                          │
│    ├─ {path}/4_portfolio/                                           │
│    │   └─ final_trade_decision_report.md                            │
│    └─ {path}/complete_report.md (合并总报告)                          │
│                                                                     │
│  [5.5] 屏幕显示完整报告 (用户确认)                                     │
│    └─ Rich Markdown Panel 渲染所有节                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 分支切分点建议

以下是适合切出新功能分支的编号位置：

| 编号 | 环节 | 适合的功能分支 |
|------|------|---------------|
| [0.2] | 自更新检查 | 添加新的更新源 / 更新策略 |
| [1.2]-[1.3] | 参数采集 | 新增参数（如资金量、风险偏好） |
| [1.5.3] | 分析师团队选择 | 新增分析师类型 |
| [1.5.5]-[1.5.6] | LLM 配置 | 新增 LLM 提供商 / 模型 |
| [2.4] | LLM 客户端初始化 | 新 LLM 客户端 / 缓存策略 |
| [2.5] | BM25 记忆系统 | 记忆系统增强 / 新检索策略 |
| [2.6] | ToolNode | 新数据工具 / 工具路由 |
| [3.2.1]-[3.2.4] | 分析师链 | 单个分析师增强 / 新分析师 |
| [3.3]-[3.6] | 研究辩论 | 辩论策略调整 / 新增研究员角色 |
| [3.7] | 交易员 | 交易策略 / A 股规则增强 |
| [3.8]-[3.11] | 风控辩论 | 风控策略 / 新增风控角色 |
| [3.12] | 投资组合经理 | 决策合成策略 / 评级算法 |
| [5.2] | 信号处理 | 评级提取精度提升 |
| [5.4] | 报告保存 | 新报告格式 / 导出格式 (PDF/HTML) |
