/* 进销项月报 + 单独下载进销项 —— 前端片段（自包含，无框架依赖）
 *
 * 用法：
 *   1) 把 HTML 片段插到「月度汇总」页面里；
 *   2) 引入本文件，并在页面就绪后调用 initTradeReport()；
 *   3) 后端需已挂载 trade_report.py 的 /api/trade-report 与 /api/trade-report/export。
 */

const TRADE_API = '/api/trade-report';

const TRADE_HEADERS = [
  '月份', '公司进项不含税金额', '进项税额', '进项总金额',
  '销项不含税金额', '销项税额', '销项总金额', '税额差额（进-销）',
  '报销普票总额', '发票构成说明', '待确认进销项',
];

const TRADE_TEMPLATE = `
<section id="tradeCard" class="trade-card">
  <div class="trade-head">
    <h2>进销项月报</h2>
    <div class="trade-actions">
      <label>年份<input id="tradeYear" type="number" min="2000" max="2100" step="1"></label>
      <button id="tradeRefresh">刷新</button>
      <button id="tradeExport" class="trade-primary">单独下载进销项</button>
    </div>
  </div>
  <p id="tradeHint" class="trade-hint"></p>
  <div class="trade-scroll">
    <table>
      <thead><tr>${TRADE_HEADERS.map(h => `<th>${h}</th>`).join('')}</tr></thead>
      <tbody id="tradeRows"></tbody>
    </table>
  </div>
</section>
`;

const TRADE_STYLE = `
.trade-card{background:#fff;border:1px solid #e8e8e8;border-radius:8px;padding:16px;margin-top:16px}
.trade-head{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
.trade-head h2{margin:0;font-size:16px;color:#333}
.trade-actions{display:flex;align-items:center;gap:8px}
.trade-actions input{width:88px;padding:6px 8px;border:1px solid #e8e8e8;border-radius:6px}
.trade-actions button{padding:6px 12px;border:1px solid #e8e8e8;background:#fff;border-radius:6px;cursor:pointer}
.trade-actions .trade-primary{background:#0d7377;border-color:#0d7377;color:#fff}
.trade-hint{color:#666;font-size:13px;margin:10px 0}
.trade-scroll{overflow-x:auto}
.trade-scroll table{width:100%;border-collapse:collapse;font-size:13px}
.trade-scroll th,.trade-scroll td{border-bottom:1px solid #e8e8e8;padding:8px 10px;text-align:left;white-space:nowrap}
.trade-scroll thead th{background:#f5f5f5;color:#333;font-weight:600}
.trade-scroll td.money{text-align:right;font-variant-numeric:tabular-nums}
`;

const tradeEsc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const tradeMoney = v => Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

let tradeData = null;

function tradeYearValue() {
  const input = document.getElementById('tradeYear');
  return Number(input && input.value ? input.value : new Date().getFullYear());
}

async function loadTradeReport() {
  const year = tradeYearValue();
  const hint = document.getElementById('tradeHint');
  hint.textContent = '正在加载进销项月报…';
  try {
    const resp = await fetch(`${TRADE_API}?year=${encodeURIComponent(year)}`);
    if (!resp.ok) throw new Error(`请求失败 ${resp.status}`);
    tradeData = await resp.json();
    renderTradeReport();
  } catch (e) {
    hint.textContent = e.message;
  }
}

function renderTradeReport() {
  const rows = (tradeData && tradeData.trade) || [];
  const tbody = document.getElementById('tradeRows');
  document.getElementById('tradeHint').textContent = rows.length
    ? `按开票日期归月，共 ${rows.length} 个月度进销项记录。`
    : '当前年份没有公司进销项记录。';
  tbody.innerHTML = rows.length
    ? rows.map(x => `<tr>
        <td>${tradeEsc(x.month)}</td>
        <td class="money">${tradeMoney(x.input_net)}</td>
        <td class="money">${tradeMoney(x.input_tax)}</td>
        <td class="money">${tradeMoney(x.input_total)}</td>
        <td class="money">${tradeMoney(x.output_net)}</td>
        <td class="money">${tradeMoney(x.output_tax)}</td>
        <td class="money">${tradeMoney(x.output_total)}</td>
        <td class="money">${tradeMoney(x.tax_diff)}</td>
        <td class="money">${tradeMoney(x.expense_total)}</td>
        <td>${tradeEsc(x.composition)}</td>
        <td>${x.unknown_count}</td>
      </tr>`).join('')
    : `<tr><td colspan="${TRADE_HEADERS.length}">当前没有公司进销项记录。</td></tr>`;
}

async function downloadTradeReport() {
  const year = tradeYearValue();
  try {
    const resp = await fetch(`${TRADE_API}/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year }),
    });
    if (!resp.ok) throw new Error(`请求失败 ${resp.status}`);
    const url = URL.createObjectURL(await resp.blob());
    const a = document.createElement('a');
    a.href = url;
    a.download = `进销项月报_${year}.xlsx`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (e) {
    alert(e.message);
  }
}

function initTradeReport(target) {
  const style = document.createElement('style');
  style.textContent = TRADE_STYLE;
  document.head.appendChild(style);

  const holder = document.createElement('div');
  holder.innerHTML = TRADE_TEMPLATE;
  const section = holder.firstElementChild;
  (target ? document.querySelector(target) : document.body).appendChild(section);

  const yearInput = document.getElementById('tradeYear');
  if (!yearInput.value) yearInput.value = new Date().getFullYear();
  document.getElementById('tradeRefresh').onclick = loadTradeReport;
  yearInput.onchange = loadTradeReport;
  document.getElementById('tradeExport').onclick = downloadTradeReport;
  loadTradeReport();
}