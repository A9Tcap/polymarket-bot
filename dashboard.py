"""
Performance Dashboard — serves a live web dashboard showing bot performance
Run alongside the bot on Railway
"""

import json
import os
import asyncio
from datetime import datetime
from aiohttp import web

TRACKER_FILE = "simulated_trades.jsonl"
RESULTS_FILE = "performance_results.json"

HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trading Bot Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0a0f;
    --surface: #111118;
    --border: #1e1e2e;
    --accent: #00ff88;
    --accent2: #ff3366;
    --accent3: #3399ff;
    --text: #e0e0e0;
    --muted: #555566;
    --win: #00ff88;
    --loss: #ff3366;
    --pending: #3399ff;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Space Mono', monospace;
    min-height: 100vh;
    padding: 24px;
    background-image: 
      radial-gradient(ellipse at 20% 20%, rgba(0,255,136,0.03) 0%, transparent 60%),
      radial-gradient(ellipse at 80% 80%, rgba(51,153,255,0.03) 0%, transparent 60%);
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 32px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }

  .logo {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 22px;
    letter-spacing: -0.5px;
  }

  .logo span { color: var(--accent); }

  .live-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 2px;
  }

  .live-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--accent);
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.8); }
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }

  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.2s;
  }

  .stat-card:hover { border-color: var(--accent); }

  .stat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
  }

  .stat-card.green::before { background: var(--accent); }
  .stat-card.red::before { background: var(--accent2); }
  .stat-card.blue::before { background: var(--accent3); }
  .stat-card.yellow::before { background: #ffcc00; }

  .stat-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--muted);
    margin-bottom: 10px;
  }

  .stat-value {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 32px;
    line-height: 1;
  }

  .stat-value.positive { color: var(--win); }
  .stat-value.negative { color: var(--loss); }
  .stat-value.neutral { color: var(--text); }
  .stat-value.blue { color: var(--accent3); }

  .stat-sub {
    font-size: 11px;
    color: var(--muted);
    margin-top: 6px;
  }

  .section-title {
    font-family: 'Syne', sans-serif;
    font-weight: 600;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 3px;
    color: var(--muted);
    margin-bottom: 16px;
  }

  .trades-table {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 32px;
  }

  .table-header {
    display: grid;
    grid-template-columns: 2fr 80px 80px 80px 80px 100px;
    padding: 12px 20px;
    background: rgba(255,255,255,0.02);
    border-bottom: 1px solid var(--border);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--muted);
  }

  .trade-row {
    display: grid;
    grid-template-columns: 2fr 80px 80px 80px 80px 100px;
    padding: 14px 20px;
    border-bottom: 1px solid var(--border);
    font-size: 12px;
    align-items: center;
    transition: background 0.15s;
  }

  .trade-row:last-child { border-bottom: none; }
  .trade-row:hover { background: rgba(255,255,255,0.02); }

  .trade-question {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding-right: 16px;
    color: var(--text);
  }

  .badge {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
  }

  .badge.yes { background: rgba(0,255,136,0.12); color: var(--win); }
  .badge.no { background: rgba(255,51,102,0.12); color: var(--loss); }
  .badge.win { background: rgba(0,255,136,0.12); color: var(--win); }
  .badge.loss { background: rgba(255,51,102,0.12); color: var(--loss); }
  .badge.pending { background: rgba(51,153,255,0.12); color: var(--pending); }
  .badge.high { background: rgba(0,255,136,0.08); color: var(--win); }
  .badge.medium { background: rgba(255,204,0,0.08); color: #ffcc00; }

  .pnl-positive { color: var(--win); font-weight: 700; }
  .pnl-negative { color: var(--loss); font-weight: 700; }
  .pnl-pending { color: var(--muted); }

  .empty-state {
    padding: 60px 20px;
    text-align: center;
    color: var(--muted);
  }

  .empty-state .emoji { font-size: 40px; margin-bottom: 16px; }
  .empty-state p { font-size: 13px; line-height: 1.8; }

  .refresh-bar {
    text-align: center;
    font-size: 11px;
    color: var(--muted);
    padding: 8px;
  }

  .win-bar-container {
    margin-bottom: 32px;
  }

  .win-bar-track {
    height: 6px;
    background: var(--border);
    border-radius: 3px;
    overflow: hidden;
    margin-top: 8px;
  }

  .win-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), #00cc6a);
    border-radius: 3px;
    transition: width 1s ease;
  }
</style>
</head>
<body>

<header>
  <div class="logo">BOT<span>TRACK</span></div>
  <div class="live-badge">
    <div class="live-dot"></div>
    Live — refreshes every 30s
  </div>
</header>

<div class="stats-grid" id="stats"></div>

<div class="win-bar-container" id="winbar"></div>

<div class="section-title">Simulated Trade Log</div>
<div class="trades-table" id="trades"></div>

<div class="refresh-bar" id="refreshbar">Last updated: —</div>

<script>
async function fetchData() {
  try {
    const r = await fetch('/api/performance');
    return await r.json();
  } catch(e) {
    return null;
  }
}

function fmt(n, prefix='$') {
  if (n === null || n === undefined) return '—';
  const abs = Math.abs(n).toFixed(2);
  return (n >= 0 ? '+' : '-') + prefix + abs;
}

function render(data) {
  const r = data.results;
  const trades = data.trades;

  const winRate = r.resolved > 0 ? (r.wins / r.resolved * 100).toFixed(1) : '—';
  const roi = r.total_staked > 0 ? (r.total_pnl / r.total_staked * 100).toFixed(1) : '—';
  const pnlClass = r.total_pnl >= 0 ? 'positive' : 'negative';
  const roiClass = parseFloat(roi) >= 0 ? 'positive' : 'negative';

  // Use real Kalshi balance if available
  const kalshi = data.kalshi || {};
  const realBalance = kalshi.balance != null ? kalshi.balance : null;
  const startingBalance = 1500;
  const realPnl = realBalance != null ? realBalance - startingBalance : null;
  const realPnlClass = realPnl != null ? (realPnl >= 0 ? 'positive' : 'negative') : '';

  document.getElementById('stats').innerHTML = `
    <div class="stat-card ${realPnl != null ? (realPnl >= 0 ? 'green' : 'red') : (r.total_pnl >= 0 ? 'green' : 'red')}">
      <div class="stat-label">Kalshi Balance</div>
      <div class="stat-value ${realPnlClass}">${realBalance != null ? '$' + realBalance.toFixed(2) : '—'}</div>
      <div class="stat-sub">P&L: ${realPnl != null ? (realPnl >= 0 ? '+' : '') + '$' + realPnl.toFixed(2) : '—'}</div>
    </div>
    <div class="stat-card blue">
      <div class="stat-label">Open Positions</div>
      <div class="stat-value blue">${kalshi.positions ? kalshi.positions.length : '—'}</div>
      <div class="stat-sub">${kalshi.positions ? kalshi.positions.map(p => p.ticker.split('-')[0]).join(', ') : 'none'}</div>
    </div>
    <div class="stat-card blue">
      <div class="stat-label">Win Rate</div>
      <div class="stat-value blue">${winRate !== '—' ? winRate + '%' : '—'}</div>
      <div class="stat-sub">${r.wins}W / ${r.losses}L of ${r.resolved} resolved</div>
    </div>
    <div class="stat-card yellow">
      <div class="stat-label">Bot Signals</div>
      <div class="stat-value neutral">${r.total_simulated}</div>
      <div class="stat-sub">${r.total_simulated - r.resolved} pending resolution</div>
    </div>
    <div class="stat-card ${parseFloat(roi) >= 0 ? 'green' : 'red'}">
      <div class="stat-label">Sim ROI</div>
      <div class="stat-value ${roiClass}">${roi !== '—' ? (parseFloat(roi) >= 0 ? '+' : '') + roi + '%' : '—'}</div>
      <div class="stat-sub">simulated return</div>
    </div>
  `;

  // Win rate bar
  if (r.resolved > 0) {
    const pct = (r.wins / r.resolved * 100).toFixed(1);
    document.getElementById('winbar').innerHTML = `
      <div class="section-title">Win Rate Progress</div>
      <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted)">
        <span>${r.wins} wins</span><span>${pct}%</span><span>${r.losses} losses</span>
      </div>
      <div class="win-bar-track">
        <div class="win-bar-fill" style="width:${pct}%"></div>
      </div>
    `;
  }

  // Trades table
  if (!trades || trades.length === 0) {
    document.getElementById('trades').innerHTML = `
      <div class="empty-state">
        <div class="emoji">🤖</div>
        <p>No simulated trades yet.<br>The bot is scanning markets — first trades will appear here soon.</p>
      </div>
    `;
    return;
  }

  const rows = trades.slice().reverse().map(t => {
    const dir = t.direction === 'BUY_YES' ? 'yes' : 'no';
    const dirLabel = t.direction === 'BUY_YES' ? 'YES' : 'NO';
    const conf = (t.confidence || '').toLowerCase();

    let statusBadge, pnlDisplay;
    if (!t.resolved) {
      statusBadge = '<span class="badge pending">OPEN</span>';
      pnlDisplay = '<span class="pnl-pending">pending</span>';
    } else if (t.won) {
      statusBadge = '<span class="badge win">WIN</span>';
      pnlDisplay = `<span class="pnl-positive">+$${t.pnl.toFixed(2)}</span>`;
    } else {
      statusBadge = '<span class="badge loss">LOSS</span>';
      pnlDisplay = `<span class="pnl-negative">-$${Math.abs(t.pnl).toFixed(2)}</span>`;
    }

    return `
      <div class="trade-row">
        <div class="trade-question" title="${t.question}">${t.question}</div>
        <div><span class="badge ${dir}">${dirLabel}</span></div>
        <div>$${(t.size_usdc||0).toFixed(0)}</div>
        <div><span class="badge ${conf}">${t.confidence||'—'}</span></div>
        <div>${statusBadge}</div>
        <div>${pnlDisplay}</div>
      </div>
    `;
  }).join('');

  document.getElementById('trades').innerHTML = `
    <div class="table-header">
      <div>Market</div>
      <div>Side</div>
      <div>Stake</div>
      <div>Conf</div>
      <div>Result</div>
      <div>P&L</div>
    </div>
    ${rows}
  `;

  document.getElementById('refreshbar').textContent = 
    'Last updated: ' + new Date().toLocaleTimeString();
}

async function update() {
  const data = await fetchData();
  if (data) render(data);
}

update();
setInterval(update, 30000);
</script>
</body>
</html>'''


async def handle_dashboard(request):
    return web.Response(text=HTML, content_type='text/html')


async def fetch_kalshi_data():
    """Fetch real balance and positions from Kalshi API."""
    import time
    import base64
    import aiohttp
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend

    api_key = os.getenv('KALSHI_API_KEY')
    private_key_str = os.getenv('KALSHI_PRIVATE_KEY', '')

    def get_headers(method, path):
        timestamp = str(int(time.time() * 1000))
        message = timestamp + method.upper() + path
        key_str = private_key_str.strip().replace('\\n', '\n')
        try:
            private_key = serialization.load_pem_private_key(key_str.encode(), password=None, backend=default_backend())
            sig = private_key.sign(message.encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256.digest_size), hashes.SHA256())
            return {
                'KALSHI-ACCESS-KEY': api_key,
                'KALSHI-ACCESS-SIGNATURE': base64.b64encode(sig).decode(),
                'KALSHI-ACCESS-TIMESTAMP': timestamp,
                'Content-Type': 'application/json',
            }
        except:
            return {}

    base_url = 'https://api.elections.kalshi.com'
    result = {'balance': None, 'positions': [], 'settled': []}

    try:
        async with aiohttp.ClientSession() as session:
            # Fetch balance
            path = '/trade-api/v2/portfolio/balance'
            async with session.get(f"{base_url}{path}", headers=get_headers('GET', path),
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    balance_cents = data.get('balance', 0)
                    result['balance'] = balance_cents / 100

            # Fetch open positions
            path = '/trade-api/v2/portfolio/positions'
            async with session.get(f"{base_url}{path}", headers=get_headers('GET', path),
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for pos in data.get('market_positions', []):
                        ticker = pos.get('ticker', '')
                        yes_pos = float(pos.get('position', 0))
                        value = float(pos.get('market_exposure', 0) or 0) / 100
                        if yes_pos != 0:
                            result['positions'].append({
                                'ticker': ticker,
                                'position': yes_pos,
                                'value': value,
                            })

            # Fetch recent settlements
            path = '/trade-api/v2/portfolio/settlements?limit=20'
            async with session.get(f"{base_url}{path}", headers=get_headers('GET', path),
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for s in data.get('settlements', []):
                        revenue = float(s.get('revenue', 0) or 0) / 100
                        result['settled'].append({
                            'ticker': s.get('ticker', ''),
                            'revenue': revenue,
                            'settled_time': s.get('settled_time', ''),
                        })
    except Exception as e:
        pass

    return result


async def handle_api(request):
    results = {}
    trades = []

    if os.path.exists('performance_results.json'):
        with open('performance_results.json', 'r') as f:
            results = json.load(f)

    if os.path.exists('simulated_trades.jsonl'):
        with open('simulated_trades.jsonl', 'r') as f:
            for line in f:
                try:
                    trades.append(json.loads(line.strip()))
                except:
                    pass

    if not results:
        results = {
            'total_simulated': 0,
            'resolved': 0,
            'wins': 0,
            'losses': 0,
            'total_pnl': 0.0,
            'total_staked': 0.0,
        }

    # Fetch live Kalshi data
    kalshi = await fetch_kalshi_data()

    # Calculate real P&L from settlements
    if kalshi['settled']:
        real_pnl = sum(s['revenue'] for s in kalshi['settled'])
        results['kalshi_balance'] = kalshi['balance']
        results['kalshi_pnl'] = real_pnl
        results['kalshi_positions'] = len(kalshi['positions'])
        results['kalshi_settlements'] = kalshi['settled'][:10]
    else:
        results['kalshi_balance'] = kalshi['balance']
        results['kalshi_positions'] = len(kalshi['positions'])

    return web.json_response({'results': results, 'trades': trades, 'kalshi': kalshi})


async def start_dashboard():
    app = web.Application()
    app.router.add_get('/', handle_dashboard)
    app.router.add_get('/api/performance', handle_api)

    port = int(os.getenv('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Dashboard running on port {port}")
    return runner
