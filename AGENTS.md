# AGENTS.md

本仓库是小米运动健康亲友数据 SDK（`mi_fitness`）。本文件说明 agent 如何查询数据。

## 关键约束：数据来源是「亲友关系」

数据只能通过**亲友共享**获取，没有任何"查自己"的接口。

- 登录账号 A，只能查询 **A 的亲友列表里的人**（对方主动共享给 A 的数据）
- 用 A 自己或其他陌生账号的 UID 查询，会返回业务错误码 `-4002001`（非亲友关系）

**常见用法：查自己的数据。** 若只有一个小米账号，可用一个"代理账号"完成：

1. 主账号 B（你本人，真正产生健康数据的账号）在 App 里把数据共享给代理账号 A
2. 本机用 **A** 登录（`uv run mi-fitness qr-login`）
3. 查询 A 的亲友列表，其中 `relative_uid=B` 的那条就是**你自己的数据**

因此「亲友列表里的人」在实际使用中往往就是使用者本人。向用户解释结果时，
不要假设对方是他人；如需确认，可对比返回的 `relative_uid` 与主账号 UID。

## 指标明细粒度

日聚合接口按天返回，**不是逐条原始采样**（除睡眠片段外，没有秒级明细）：

| 指标 | 可用明细 |
|---|---|
| `heart_rate` | 日均、静息、最大/最小、最新采样、异常次数、5 个心率区间时长 |
| `sleep` | 总时长、评分、深/浅/REM/清醒时长、均/最大/最小心率、均血氧、**睡眠片段**（入睡/醒来时刻、片段时长、醒来次数） |
| `steps` | 步数、距离、卡路里、目标 |
| `spo2` | 平均/最大/最小、偏低次数、最新采样 |
| `intensity` | 中高强度总时长（分钟） |
| `calories` | 活动卡路里 |
| `valid_stand` | 有效站立次数 |
| `weight` / `blood_pressure` | 设备测量记录（`get_fitness_data` 原始记录，按时间点）；无测量时为空列表 |

需要更细的原始数据时，用 `get_fitness_data(uid, key, start, end)` 获取
`weight` / `blood_pressure` / 异常心率等测量/事件级记录；日聚合指标
（心率区间、睡眠分期等）接口本身只提供按天汇总。

## 首选方式：CLI（输出 JSON）

所有命令在仓库根目录执行。需要先登录一次（人工扫码）：

```bash
uv run mi-fitness qr-login
```

查询命令：

```bash
uv run mi-fitness relatives                              # 亲友列表
uv run mi-fitness latest --relative 妈妈                 # 最新快照
uv run mi-fitness latest --uid 123456
uv run mi-fitness history --uid 123456 --key steps --days 7
uv run mi-fitness history --relative 妈妈 --key sleep --date 2024-06-04
uv run mi-fitness summary --relative 妈妈 --latest       # 心率+睡眠+步数
uv run mi-fitness summary --uid 123456 --date 2024-06-04
uv run mi-fitness relatives --format table               # 表格输出
```

`--key` 可选值：`heart_rate`、`sleep`、`steps`、`blood_pressure`、`calories`、
`valid_stand`、`intensity`、`weight`、`spo2`。

## MCP 方式（若客户端已配置）

服务名 `mi-fitness`，命令 `mi-fitness-mcp`（stdio）。工具：

| 工具 | 参数 |
|---|---|
| `list_relatives` | 无 |
| `get_latest_data` | `relative_uid` 或 `relative` |
| `get_shared_data_types` | `relative_uid` 或 `relative` |
| `get_history` | `key`、`days`、`relative_uid` 或 `relative`、可选 `query_date` |
| `get_daily_summary` | `relative_uid` 或 `relative`、可选 `query_date`、`latest` |

## Token

- 默认路径：仓库根目录 `token.json`
- 覆盖方式：`--token PATH` 或环境变量 `MI_FITNESS_TOKEN`
- 内含长期有效凭证，**不要提交到 git、不要贴到对话里**
- token 过期会自动用 `passToken` 刷新，无需重新扫码

## 登录（唯一需要人工的步骤）

```bash
uv run mi-fitness qr-login
```

终端会输出二维码图片 URL 和浏览器链接，需用小米运动健康 App 扫码。
agent 无法代劳，遇到未登录时应提示用户自行扫码。

## 错误含义

| 错误 | 含义 / 处理 |
|---|---|
| `AuthError: Token 文件不存在` | 还未登录，让用户执行 `qr-login` |
| `TokenExpiredError` | token 失效且刷新失败，需重新扫码 |
| `FamilyMemberNotFoundError`（`code=-4002001`） | 非亲友关系，含**查询自己 UID** 的情况 |
| `DataNotSharedError` | 对方未共享该数据类型 |
| `DataOutOfSharedTimeScopeError` | 查询日期超出对方允许的共享时间范围 |

## 时区

所有日期按**中国标准时间（UTC+8）**切分自然日。`days` 取值范围 `1..365`。

## 开发校验

```bash
uv run ruff check src/ tests/unit/ examples/
uv run ruff format --check src/ tests/unit/ examples/
uv run basedpyright src/ tests/unit/
uv run pytest
```
