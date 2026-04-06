"""
Dashboard — pulls 100% real data from Kalshi API. No internal tracking.
"""

import json
import os
import asyncio
import time
import base64
from datetime import datetime
from aiohttp import web
import aiohttp
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

STARTING_BALANCE = 1500.00

HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kalshi Trading Bot</title>
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
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Space Mono', monospace;
    min-height: 100vh;
    padding: 24px;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 32px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }
  .logo { font-family: 'Syne', sans-serif; font-weight: 800; font-size: 22px; }
  .logo span { color: var(--accent); }
  .live-badge {
    display: flex; align-items: center; gap: 8px;
    font-size: 11px; color: var(--muted);
    text-transform: uppercase; letter-spacing: 2px;
  }
  .live-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--accent); animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; } 50% { opacity: 0.3; }
  }
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px; margin-bottom: 32px;
  }
  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px; padding: 20px;
  }
  .stat-card.green { border-color: rgba(0,255,136,0.3); }
  .stat-card.red { border-color: rgba(255,51,102,0.3); }
  .stat-card.blue { border-color: rgba(51,153,255,0.3); }
  .stat-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
  .stat-value { font-size: 28px; font-weight: 700; font-family: 'Syne', sans-serif; }
  .stat-value.positive { color: var(--win); }
  .stat-value.negative { color: var(--loss); }
  .stat-value.blue { color: var(--accent3); }
  .stat-value.neutral { color: var(--text); }
  .stat-sub { font-size: 11px; color: var(--muted); margin-top: 6px; }
  .section { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 20px; }
  .section-title { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 1px; padding: 8px 12px; border-bottom: 1px solid var(--border); }
  td { padding: 12px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; }
  .tag-yes { background: rgba(0,255,136,0.15); color: var(--win); }
  .tag-no { background: rgba(255,51,102,0.15); color: var(--loss); }
  .tag-open { background: rgba(51,153,255,0.15); color: var(--accent3); }
  .tag-win { background: rgba(0,255,136,0.15); color: var(--win); }
  .tag-loss { background: rgba(255,51,102,0.15); color: var(--loss); }
  .empty { text-align: center; color: var(--muted); padding: 40px; font-size: 13px; }
  .updated { font-size: 11px; color: var(--muted); text-align: right; margin-top: 8px; }
</style>
</head>
<body>
<header>
  <div class="logo">Kalshi<span>Bot</span></div>
  <div class="live-badge"><div class="live-dot"></div>Live Data from Kalshi</div>
</header>

<div class="stats-grid" id="stats">
  <div class="stat-card"><div class="stat-label">Loading...</div></div>
</div>

<div class="section">
  <div class="section-title">Open Positions</div>
  <div id="positions"><div class="empty">Loading...</div></div>
</div>

<div class="section">
  <div class="section-title">Recent Settlements (Last 20)</div>
  <div id="settlements"><div class="empty">Loading...</div></div>
</div>

<div class="updated" id="updated"></div>

<script>
async function fetchData() {
  try {
    const r = await fetch('/api/performance');
    if (!r.ok) throw new Error('API error');
    const data = await r.json();
    render(data);
  } catch(e) {
    document.getElementById('stats').innerHTML = '<div class="stat-card"><div class="stat-label">Error loading data</div><div class="stat-sub">' + e.message + '</div></div>';
  }
}

function fmt(n) {
  if (n == null) return '—';
  const sign = n >= 0 ? '+' : '-';
  return sign + '$' + Math.abs(n).toFixed(2);
}

function render(data) {
  const k = data.kalshi || {};
  const balance = k.balance;
  const cash = k.cash;
  const posValue = k.positions_value;
  const startingBalance = ''' + str(STARTING_BALANCE) + ''';
  const pnl = balance != null ? balance - startingBalance : null;
  const pnlPct = pnl != null ? (pnl / startingBalance * 100).toFixed(2) : null;
  const pnlClass = pnl != null ? (pnl >= 0 ? 'positive' : 'negative') : 'neutral';
  const cardClass = pnl != null ? (pnl >= 0 ? 'green' : 'red') : '';

  const positions = k.positions || [];
  const settled = k.settled || [];
  const wins = settled.filter(s => s.revenue > 0).length;
  const losses = settled.filter(s => s.revenue <= 0).length;
  const totalRevenue = settled.reduce((a, s) => a + s.revenue, 0);
  const winRate = settled.length > 0 ? (wins / settled.length * 100).toFixed(1) : null;

  document.getElementById('stats').innerHTML = `
    <div class="stat-card ${cardClass}">
      <div class="stat-label">Portfolio Value</div>
      <div class="stat-value ${pnlClass}">$${balance != null ? balance.toFixed(2) : '—'}</div>
      <div class="stat-sub">Started at $${startingBalance.toFixed(2)}</div>
    </div>
    <div class="stat-card ${cardClass}">
      <div class="stat-label">ROI</div>
      <div class="stat-value ${pnlClass}">${pnl != null ? fmt(pnl) : '—'}</div>
      <div class="stat-sub">${pnlPct != null ? pnlPct + '% return' : '—'}</div>
    </div>
    <div class="stat-card blue">
      <div class="stat-label">Cash Available</div>
      <div class="stat-value blue">$${cash != null ? cash.toFixed(2) : '—'}</div>
      <div class="stat-sub">$${posValue != null ? posValue.toFixed(2) : '—'} in positions</div>
    </div>
    <div class="stat-card blue">
      <div class="stat-label">Open Positions</div>
      <div class="stat-value blue">${positions.length}</div>
      <div class="stat-sub">active bets</div>
    </div>
    <div class="stat-card ${wins > losses ? 'green' : losses > wins ? 'red' : ''}">
      <div class="stat-label">Win Rate</div>
      <div class="stat-value ${wins > losses ? 'positive' : losses > wins ? 'negative' : 'neutral'}">${winRate != null ? winRate + '%' : '—'}</div>
      <div class="stat-sub">${wins}W / ${losses}L from ${settled.length} settled</div>
    </div>
    <div class="stat-card ${totalRevenue >= 0 ? 'green' : 'red'}">
      <div class="stat-label">Settled P&L</div>
      <div class="stat-value ${totalRevenue >= 0 ? 'positive' : 'negative'}">${fmt(totalRevenue)}</div>
      <div class="stat-sub">from closed trades</div>
    </div>
  `;

  // Positions table
  if (positions.length === 0) {
    document.getElementById('positions').innerHTML = '<div class="empty">No open positions — check Kalshi app</div>';
  } else {
    document.getElementById('positions').innerHTML = `
      <table>
        <thead><tr><th>Market</th><th>Side</th><th>Contracts</th><th>Cost</th><th>Market Value</th><th>Payout if Win</th></tr></thead>
        <tbody>${positions.map(p => `
          <tr>
            <td style="font-size:11px">${p.ticker}</td>
            <td><span class="tag ${p.side === 'YES' ? 'tag-yes' : 'tag-no'}">${p.side}</span></td>
            <td>${Math.abs(p.contracts)}</td>
            <td>$${(p.cost || 0).toFixed(2)}</td>
            <td>$${(p.market_value || 0).toFixed(2)}</td>
            <td>$${Math.abs(p.contracts).toFixed(2)}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
  }

  // Settlements table
  if (settled.length === 0) {
    document.getElementById('settlements').innerHTML = '<div class="empty">No settled trades yet</div>';
  } else {
    document.getElementById('settlements').innerHTML = `
      <table>
        <thead><tr><th>Market</th><th>Result</th><th>Revenue</th><th>Date</th></tr></thead>
        <tbody>${settled.map(s => `
          <tr>
            <td>${s.ticker}</td>
            <td><span class="tag ${s.revenue > 0 ? 'tag-win' : 'tag-loss'}">${s.revenue > 0 ? 'WIN' : 'LOSS'}</span></td>
            <td class="${s.revenue > 0 ? 'positive' : 'negative'}" style="color:${s.revenue > 0 ? 'var(--win)' : 'var(--loss)'}">${fmt(s.revenue)}</td>
            <td>${s.settled_time ? s.settled_time.substring(0, 10) : '—'}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
  }

  document.getElementById('updated').textContent = 'Last updated: ' + new Date().toLocaleTimeString();
}

fetchData();
setInterval(fetchData, 30000);
</script>
</body>
</html>'''


def get_kalshi_headers(method, path):
    api_key = os.getenv('KALSHI_API_KEY')
    private_key_str = os.getenv('KALSHI_PRIVATE_KEY', '')
    timestamp = str(int(time.time() * 1000))
    message = timestamp + method.upper() + path.split('?')[0]
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
    except Exception as e:
        return {}


async def fetch_kalshi_data():
    base_url = 'https://api.elections.kalshi.com'
    result = {'balance': None, 'cash': None, 'positions_value': None, 'positions': [], 'settled': []}

    try:
        async with aiohttp.ClientSession() as session:
            # Balance
            path = '/trade-api/v2/portfolio/balance'
            async with session.get(f"{base_url}{path}", headers=get_kalshi_headers('GET', path),
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    cash = float(data.get('balance', 0)) / 100
                    pos_val = float(data.get('portfolio_value', 0) or 0) / 100
                    result['cash'] = cash
                    result['positions_value'] = pos_val
                    result['balance'] = cash + pos_val

            # Positions
            path = '/trade-api/v2/portfolio/positions'
            async with session.get(f"{base_url}{path}", headers=get_kalshi_headers('GET', path),
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Try both possible keys Kalshi might use
                    positions_list = data.get('market_positions', data.get('positions', []))
                    for pos in positions_list:
                        # position can be positive (YES) or negative (NO)
                        # Also check yes_position and no_position fields
                        yes_pos = float(pos.get('yes_position', 0) or 0)
                        no_pos = float(pos.get('no_position', 0) or 0)
                        raw_pos = float(pos.get('position', 0) or 0)
                        
                        if yes_pos > 0:
                            contracts = yes_pos
                            side = 'YES'
                        elif no_pos > 0:
                            contracts = no_pos
                            side = 'NO'
                        elif raw_pos > 0:
                            contracts = raw_pos
                            side = 'YES'
                        elif raw_pos < 0:
                            contracts = abs(raw_pos)
                            side = 'NO'
                        else:
                            continue

                        cost = float(pos.get('total_cost', 0) or 0) / 100
                        market_value = float(pos.get('market_exposure', 0) or 0) / 100
                        ticker = pos.get('ticker', '')
                        
                        result['positions'].append({
                            'ticker': ticker,
                            'side': side,
                            'contracts': contracts,
                            'cost': cost,
                            'market_value': market_value,
                        })

            # Settlements
            path = '/trade-api/v2/portfolio/settlements?limit=20'
            async with session.get(f"{base_url}{path}", headers=get_kalshi_headers('GET', path),
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


async def handle_dashboard(request):
    return web.Response(text=HTML, content_type='text/html')


async def handle_api(request):
    kalshi = await fetch_kalshi_data()
    return web.json_response({'kalshi': kalshi})


async def start_dashboard():
    app = web.Application()
    app.router.add_get('/', handle_dashboard)
    app.router.add_get('/api/performance', handle_api)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("Dashboard running on port 8080")
    return runner
