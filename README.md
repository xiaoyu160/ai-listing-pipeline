# AI Listing Pipeline

> 电商商品「标题 / 卖点 / 关键词」的**批量生成 + 规则校验 + 自动修复**流水线。
> 输入一张商品表，输出可直接上架的结果表和审核报告。

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![tests](https://img.shields.io/badge/tests-20%20passed-brightgreen)]()

---

## 为什么做这个

电商运营每天要给几十上百个 SKU 写标题和卖点，纯人工的痛点是：慢、风格不统一、容易踩平台违禁词。
直接调大模型也不行 —— **模型输出的是"一段话"，不是"可上架的字段"**：

- 标题超 60 字被平台截断；
- 写进"全网最低"被判定违规下架；
- 返回 JSON 带了 Markdown 代码块，程序解析直接崩；
- 批量跑 200 条，中途限流挂掉，前面全白跑。

这个项目要解决的就是这层"最后一公里"：**把模型的自由文本，变成稳定、可校验、可批量、可重跑的结构化数据。**

## 它做了什么

| 能力 | 实现 |
| --- | --- |
| 批量生成 | 线程池并发（可配置 workers），自适应服务商 QPS |
| 容错解析 | 兼容裸 JSON / ```json 代码块 / 前后带废话三种返回 |
| 结构校验 | 字段缺失、类型错误 → 抛 `SchemaError`，不污染下游 |
| 规则校验 | 字数、违禁词、必含词、卖点条数、表情/HTML/营销符号、与原标重复度 |
| 自动修复 | 把"问题清单"回灌模型再问一次，只改不合格项，最多 1 轮 |
| 断点续跑 | 每条结果落 `checkpoint.jsonl`，中断重跑自动跳过已完成 |
| 成本可见 | 统计 token 与估算费用，跑之前就知道这批要花多少钱 |
| 交付物 | 结果表 xlsx + 上架表 csv（utf-8-sig，Excel 直接打开不乱码）+ 运行报告 md |

## 架构

```
                       config/default.yaml  (模型 / 并发 / 规则 / 列映射)
                                │
商品表 csv/xlsx ──► tableio ──► Pipeline ──────────────────────────────┐
                                │                                      │
                                ├─► prompts   渲染模板($var 占位)      │
                                ├─► llm       openai_compat | mock     │
                                ├─► schema    extract_json → Listing    │
                                ├─► validator 规则校验 → Issue[]       │
                                │      └─ 有 error → 带着问题重问 1 轮 │
                                └─► checkpoint  jsonl 追加写 ◄─────────┘
                                                │
                    ┌───────────────────────────┼──────────────────────┐
                    ▼                           ▼                      ▼
             out/listings.xlsx          out/listing_export.csv     out/report.md
```

分层原则：**业务逻辑不感知模型供应商**。`llm/` 只暴露 `chat(system, user) -> ChatResult`，
换 DeepSeek / 通义 / OpenAI 只改一行配置；`MockClient` 让全链路可以离线跑通、可单测。

## 快速开始

```bash
git clone <repo>
cd ai-listing-pipeline
pip install -e ".[dev]"

# 1) 不联网先跑通链路（用内置 mock 模型）
ai-listing run --input data/sample_products.csv --provider mock

# 2) 接真实模型
cp .env.example .env        # 填入 DEEPSEEK_API_KEY
ai-listing run --input data/sample_products.csv --limit 5
```

输出：

```
out/
├── listings.xlsx          # 结果表：标题 / 卖点 / 关键词 / 校验状态 / 问题明细 / 耗时 / tokens
├── listing_export.csv     # 上架表：可直接导入后台
├── report.md              # 运行报告：通过率 / 成本 / 需人工确认的条目
└── checkpoint.jsonl       # 断点
```

## 规则校验清单

规则全部写在 `config/default.yaml` 的 `rules` 下，改配置即改策略，不用动代码：

| 检查项 | 级别 | 说明 |
| --- | --- | --- |
| 标题字数 | error | 默认 12–60 字，英文数字按 0.5 字符折算 |
| 违禁词 | error | `data/banned_words.txt`，可替换成平台官方词库 |
| 必含词 | error | 全局配置 + 每行数据的 `关键词` 列，保证检索命中 |
| 卖点条数 / 单条长度 | error / warn | 条数不足只告警，超长必须改 |
| 表情 / HTML / 营销符号 | error | `🔥`、`<b>`、`!!!`、`★★★` 一律拒绝 |
| 与原商品名重复度 | warn | `SequenceMatcher` 相似度 > 65% 提示改写不足 |
| 卖点重复 | error | 归一化后去重比较 |

## 一次真实的运行

12 个服装 SKU，mock 模型跑通全链路：

```
完成：通过 12/12（修复后通过 0），6877 tokens，约 ￥0.0089
```

`pytest`：**20 passed**，覆盖 JSON 容错解析、规则命中、修复轮、重试退避、断点续跑、成本统计。

## 目录

```
src/ai_listing/
├── cli.py          # 命令行入口
├── pipeline.py     # 并发 / 重试 / 修复 / checkpoint
├── validator.py    # 规则校验（本项目最核心的部分）
├── schema.py       # JSON 容错解析 + 数据结构校验
├── prompts.py      # 模板渲染
├── tableio.py      # 表格读写与列映射
├── export.py       # 上架表 + 运行报告
├── config.py       # YAML / .env 配置
└── llm/            # 客户端抽象与实现（openai_compat / mock）
```

## 设计取舍

1. **为什么校验放在模型外面，而不是靠 prompt？** Prompt 只能提高概率，不能保证结果。
   平台规则是会变的硬约束，必须由确定性代码兜底。模型负责"写得好"，代码负责"不出事"。
2. **为什么修复只做一轮？** 两轮以上通常说明这条商品信息本身残缺（属性没填），
   继续重试只是浪费钱，不如标记失败交人工。这也是"失败也要可解释"的设计。
3. **为什么用 checkpoint 而不是一次性重跑？** 批量任务的天敌是"跑到 180/200 被限流"。
   jsonl 追加写 + 幂等跳过，让任务可以随时中断、随时继续。

## Roadmap

- [ ] 接入平台官方违禁词库与类目规则（按类目差异化）
- [ ] 标题 A/B 版本生成 + 点击率回填，形成"生成 → 投放 → 数据反馈"闭环
- [ ] 多模态：商品图 → 卖点提取（对应 AI 出款图 / 视觉选品场景）
- [ ] 简单 Web 界面（上传表格 → 预览 → 导出）

## License

MIT
