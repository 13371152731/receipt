# 进销项月报 + 单独下载进销项（独立功能包）

从 `fapiao/invoice_demo` 中抽取出来的一个功能：把公司往来的**进项 / 销项发票按月归集**，
在页面渲染「进销项月报」表格，并提供**只导出这一张表**的 Excel 下载按钮。

已去掉对原项目 `store` / `auth` / `extraction` 的依赖，可直接嵌入任何 FastAPI + 原生 JS 的项目。

## 文件清单

| 文件 | 作用 |
| --- | --- |
| `trade_report.py` | 后端：进销项方向识别 + 按月归集 + Excel 导出 + 可选 FastAPI 路由 |
| `trade_report_frontend.js` | 前端：表格渲染 + 「单独下载进销项」按钮（无框架依赖） |
| `demo_selftest.py` | 自测脚本，含示例数据；运行 `python demo_selftest.py` 即可验证 |
| `demo_output.xlsx` | 自测生成的示例导出结果，可直接打开看格式 |

数据流：`标准发票记录 -> build_trade_report() -> 前端表格 / export_trade_workbook() -> xlsx`

## 一、后端接入

1. 把 `trade_report.py` 复制到你的项目里（例如 `app/trade_report.py`）。
2. 修改文件顶部两行为**你自己公司的**信息，这是判断进项/销项的唯一依据：
   ```python
   OUR_TAX_ID = '你的公司税号'
   OUR_NAMES = {'你的公司全称'}
   ```
   购买方是我方 → 进项；销售方是我方 → 销项；都不是 → 待确认进销项。
3. 在 FastAPI 启动处注册路由，并提供一个返回全部发票记录的函数：
   ```python
   from trade_report import register_trade_routes

   def all_invoices():
       # 返回标准发票记录列表，格式见「三、输入数据契约」
       return load_my_invoices()

   register_trade_routes(app, all_invoices)
   ```
   `guard` 是可选参数，需要鉴权时传入无参函数，不通过就自己 `raise HTTPException`：
   ```python
   register_trade_routes(app, all_invoices, guard=lambda: require_admin())
   ```
4. 注册后会得到两个接口：

   | 接口 | 说明 |
   | --- | --- |
   | `GET /api/trade-report?year=2026` | 返回 `{"year": 2026, "trade": [...]}`，`year` 传 0 或不传表示不限年份 |
   | `POST /api/trade-report/export`，body `{"year": 2026}` | 返回只有一个 `进销项月报` sheet 的 xlsx |

   > 若路径和你现有接口冲突，用 `register_trade_routes(app, provider, prefix='/api/其他路径')` 改掉。

5. 依赖：`fastapi`、`openpyxl`。纯计算部分只用到标准库 `decimal` / `re` / `io`。

## 二、前端接入

1. 把 `trade_report_frontend.js` 引入页面。
2. 在「月度汇总」页面里选一个容器，调用：
   ```js
   initTradeReport();                 // 默认插到 body 末尾
   initTradeReport('#monthlyPage');   // 或指定挂载点
   ```
3. 组件会自渲染「进销项月报」卡片，包含年份筛选、刷新、**单独下载进销项**按钮。
   按钮下载的文件名为 `进销项月报_2026.xlsx`。
4. 如果你的后端路径不是 `/api/trade-report`，改 `trade_report_frontend.js` 顶部的 `TRADE_API`。

## 三、输入数据契约

`all_invoices()` 返回一个 list，每条是一个 dict：

必需字段：
```
invoice_date   'YYYY-MM-DD'                     开票日期
ledger         'company' | 'expense'            台账：公司往来 / 费用报销
net / tax / total                               不含税金额 / 税额 / 价税合计（字符串金额）
kind           'special' | 'ordinary' | 'train' | 'unknown'   票种
```

可选字段：
```
buyer_name / buyer_tax_id / seller_name / seller_tax_id   用于自动判断进销项方向
direction      'input' | 'output' | 'unknown'   已算好方向则直接使用，跳过自动判断
category       'special' | 'ordinary' | 'unknown'          已算好分类则直接使用
reimburser     报销人        status   审核状态        id   记录主键
```

示例：
```python
{
    'invoice_date': '2026-03-05', 'ledger': 'company', 'kind': 'special',
    'net': '1000.00', 'tax': '130.00', 'total': '1130.00',
    'buyer_tax_id': OUR_TAX_ID, 'id': 'in-1',
}
```

也兼容嵌套写法 `{'values': {...}, 'direction': ...}`，从原项目迁移时不用改数据结构。

## 四、口径说明

- 按**票面开票日期**归月，同一个月即使只有报销记录也会出一行。
- 「报销普票总额」= 当月 `ledger=expense` 且 `category=ordinary` 的价税合计之和。
- 「税额差额（进-销）」= 进项税额 − 销项税额。
- 「发票构成说明」自动拼装：进项份数 / 报销专票份数（含火车票，仅计报销）/ 销项正数普票份数 / 销项负数发票份数 / 进项负数发票份数。
- 「待确认进销项」= 该月 `direction=unknown` 的公司往来发票张数。

## 五、验证

```bash
cd deliver_trade_report
python demo_selftest.py
```
会校验方向判断、金额归集、税额差额、红冲负数统计、Excel sheet 名与表头，并生成 `demo_output.xlsx`。

## 六、对应原项目出处

| 本包内容 | 原文件位置 |
| --- | --- |
| 进销项归集计算 | `invoice_demo/service.py:192-212`（`_monthly_report_data` 的 trade 部分） |
| 导出 Excel | `invoice_demo/service.py:296-297` |
| 导出接口 | `invoice_demo/service.py:276-299` |
| 方向识别 | `invoice_demo/extraction.py:14-19`（`trade_direction`） |
| 金额解析 | `invoice_demo/extraction.py:23-32` |
| 前端表格与按钮 | `invoice_demo/static/app.js:21,60,62,88` |