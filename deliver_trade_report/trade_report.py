"""进销项月报 + 单独下载进销项表格（自包含独立模块）

从 fapiao/invoice_demo 中抽取，去掉对原项目 store / auth / extraction 的依赖，
只保留「进销项方向识别 -> 按月归集 -> 导出 Excel」这一条链路。

对外提供：
    build_trade_report(invoices, year)   进销项按月归集，返回可直接喂给前端的列表
    export_trade_workbook(rows)          生成「进销项月报」xlsx 字节流
    register_trade_routes(app, provider) 可选：往 FastAPI 上挂 GET/POST 两个路由

输入契约（标准发票记录，dict）：
    必需
        invoice_date  开票日期，'YYYY-MM-DD'
        ledger        台账，'company'（公司往来）或 'expense'（费用报销）
        net/tax/total 不含税金额 / 税额 / 价税合计，字符串金额
        kind          票种，'special' | 'ordinary' | 'train' | 'unknown'
    可选
        direction     'input' | 'output' | 'unknown'，已算好则直接使用
        category      'special' | 'ordinary' | 'unknown'，已算好则直接使用
        buyer_name / buyer_tax_id / seller_name / seller_tax_id  用于自动判断进销项方向
        reimburser    报销人；status  审核状态；id  记录主键
    兼容原项目 present() 的嵌套写法：{'values': {...}, 'direction': ..., 'category': ...}
"""

from __future__ import annotations

import io
import re
from decimal import Decimal, InvalidOperation

# ---------------------------------------------------------------------------
# 配置：判断「进项 / 销项」时使用的我方公司身份。
# 购买方是我方 -> 进项；销售方是我方 -> 销项；都不是（或都是）-> 待确认。
# ---------------------------------------------------------------------------
OUR_TAX_ID = '91370102689842485K'
OUR_NAMES = {'济南翱众信息系统有限公司', '济南翱众信息系统公司'}

KINDS = {'special': '增值税专用发票', 'ordinary': '普通发票', 'train': '火车票', 'unknown': '待确认票种'}

MONTHLY_TRADE_HEADERS = [
    '月份', '公司进项不含税金额', '进项税额', '进项总金额',
    '销项不含税金额', '销项税额', '销项总金额', '税额差额（进-销）',
    '报销普票总额', '发票构成说明', '待确认进销项',
]

XLSX_MEDIA_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def clean(s):
    return re.sub(r'\s+', '', str(s)).replace('：', ':')


def amount(s):
    s = clean(s).replace('¥', '').replace('￥', '').replace(',', '').replace('，', '').replace('−', '-')
    try:
        if not re.fullmatch(r'-?\d{1,12}(?:\.\d{1,2})?', s):
            return None
        return Decimal(s).quantize(Decimal('.01'))
    except InvalidOperation:
        return None


def _money(value):
    return amount(value) or Decimal('0.00')


def _month(value):
    return value[:7] if isinstance(value, str) and len(value) >= 7 and value[4:5] == '-' else ''


def category_of(kind):
    return 'special' if kind in ['special', 'train'] else 'ordinary' if kind == 'ordinary' else 'unknown'


def trade_direction(values):
    """按税号（优先）或公司名判断进销项方向。"""
    def match(side):
        tax = clean(values.get(side + '_tax_id', '')).upper()
        return tax == OUR_TAX_ID if tax else clean(values.get(side + '_name', '')) in OUR_NAMES

    buyer, seller = match('buyer'), match('seller')
    return 'input' if buyer and not seller else 'output' if seller and not buyer else 'unknown'


def normalize_invoice(raw):
    """把一条标准记录规整成只含进销项计算所需字段的扁平结构。"""
    nested = raw.get('values') if isinstance(raw.get('values'), dict) else {}
    def pick(key):
        return raw.get(key, nested.get(key, ''))
    kind = raw.get('kind') or raw.get('kind_override') or 'unknown'
    values = {
        'invoice_date': pick('invoice_date'),
        'buyer_name': pick('buyer_name'), 'buyer_tax_id': pick('buyer_tax_id'),
        'seller_name': pick('seller_name'), 'seller_tax_id': pick('seller_tax_id'),
        'net': pick('net'), 'tax': pick('tax'), 'total': pick('total'),
    }
    return {
        'id': pick('id'),
        'invoice_date': values['invoice_date'],
        'net': values['net'], 'tax': values['tax'], 'total': values['total'],
        'kind': kind,
        'direction': raw.get('direction') or trade_direction(values),
        'category': raw.get('category') or category_of(kind),
        'ledger': raw.get('ledger', ''),
        'reimburser': raw.get('reimburser', ''),
        'status': raw.get('status', ''),
    }


def build_trade_report(invoices, year=0):
    """按月归集公司进销项，返回进销项月报数据。

    year=0 表示不限年份。金额字段以两位小数字符串返回，可直接交给前端展示。
    """
    year_text = str(year) if year else ''
    expense, company = [], []
    for raw in invoices:
        rec = normalize_invoice(raw)
        month = _month(rec['invoice_date'])
        if not month or (year_text and not month.startswith(year_text)):
            continue
        if rec['ledger'] == 'company':
            company.append(rec)
        elif rec['ledger'] == 'expense':
            expense.append(rec)

    months = sorted({_month(x['invoice_date']) for x in expense + company if _month(x['invoice_date'])}, reverse=True)

    expense_ordinary = {}
    expense_special = {}
    for p in expense:
        m = _month(p['invoice_date'])
        if p['category'] == 'ordinary':
            expense_ordinary[m] = expense_ordinary.get(m, Decimal('0.00')) + _money(p['total'])
        elif p['category'] == 'special':
            expense_special[m] = expense_special.get(m, 0) + 1

    rows = []
    for month in months:
        g = {
            'month': month,
            'input_net': Decimal('0.00'), 'input_tax': Decimal('0.00'), 'input_total': Decimal('0.00'),
            'output_net': Decimal('0.00'), 'output_tax': Decimal('0.00'), 'output_total': Decimal('0.00'),
            'expense_total': expense_ordinary.get(month, Decimal('0.00')),
            'unknown_count': 0, 'input_count': 0, 'output_count': 0,
            'expense_special_count': expense_special.get(month, 0),
            'output_negative_count': 0, 'input_negative_count': 0,
            'records': [],
        }
        for p in company:
            if _month(p['invoice_date']) != month:
                continue
            if p['id']:
                g['records'].append(p['id'])
            direction, total = p['direction'], _money(p['total'])
            if direction == 'input':
                g['input_count'] += 1
                g['input_net'] += _money(p['net']); g['input_tax'] += _money(p['tax']); g['input_total'] += total
                if total < 0:
                    g['input_negative_count'] += 1
            elif direction == 'output':
                g['output_count'] += 1
                g['output_net'] += _money(p['net']); g['output_tax'] += _money(p['tax']); g['output_total'] += total
                if total < 0:
                    g['output_negative_count'] += 1
            else:
                g['unknown_count'] += 1
        g['tax_diff'] = g['input_tax'] - g['output_tax']
        g['composition'] = (
            f"{g['input_count']}份进项发票 / {g['expense_special_count']}份报销专票（含火车票，仅计报销） / "
            f"{g['output_count']}份销项正数普票 / {g['output_negative_count']}份销项负数发票 / "
            f"{g['input_negative_count']}份进项负数发票"
        )
        rows.append({k: (str(v.quantize(Decimal('.01'))) if isinstance(v, Decimal) else v) for k, v in g.items()})
    return rows


def export_trade_workbook(trade_rows, sheet_title='进销项月报'):
    """把进销项月报列表导出成单个 xlsx（只有这一个 sheet）。"""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet(sheet_title)
    ws.append(MONTHLY_TRADE_HEADERS)
    for x in trade_rows:
        ws.append([
            x['month'], float(x['input_net']), float(x['input_tax']), float(x['input_total']),
            float(x['output_net']), float(x['output_tax']), float(x['output_total']),
            float(x['tax_diff']), float(x['expense_total']), x['composition'], x['unknown_count'],
        ])
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='1B6666')
    for col in range(1, len(MONTHLY_TRADE_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 24
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical='center', wrap_text=True)
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def register_trade_routes(app, rows_provider, prefix='/api/trade-report', guard=None, year_range=(2000, 2100)):
    """把进销项月报的查询与下载接口挂到 FastAPI 应用上。

    rows_provider: 无参可调用对象，返回全部标准发票记录列表。
    guard:         可选，无参可调用对象，用于鉴权；不通过时自行 raise HTTPException。
    """
    from fastapi import HTTPException, Request
    from fastapi.responses import Response

    def check_year(year):
        if year and not (year_range[0] <= year <= year_range[1]):
            raise HTTPException(422, '年份不合法')

    @app.get(prefix)
    def trade_report(year: int = 0):
        check_year(year)
        if guard:
            guard()
        return {'year': year or None, 'trade': build_trade_report(rows_provider(), year)}

    @app.post(prefix + '/export')
    async def trade_report_export(request: Request):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(422, '请求格式错误')
        year = body.get('year', 0) if isinstance(body, dict) else 0
        if not isinstance(year, int):
            raise HTTPException(422, '年份不合法')
        check_year(year)
        if guard:
            guard()
        payload = export_trade_workbook(build_trade_report(rows_provider(), year))
        filename = f'trade-report-{year}.xlsx' if year else 'trade-report.xlsx'
        return Response(payload, media_type=XLSX_MEDIA_TYPE,
                        headers={'Content-Disposition': f'attachment; filename="{filename}"'})