"""
Profit Taker — monitors open positions and exits when profit targets are hit.

KEY INSIGHT:
- Sports heavy-favourite NO bets (YES=8%, NO=92%): price barely moves, 
  take_profit fires when position gains 30%+ of max possible gain
- Macro positions (YES=40%, NO=60%): big price swings on news, 
  take_profit fires when position gains 50%+ of max possible gain
- Stop loss: sell if position loses 50% of entry cost

HOW IT WORKS:
  Entry: BUY_NO on Girona at YES=8% (NO=92%)
  We paid $0.92 per NO contract, bought 16 contracts for $15
  If Real Madrid goes up 2-0 and YES drops to 3%, NO is now worth $0.97
  Current profit = ($0.97 - $0.92) * 16 = $0.80
  Max profit = ($1.00 - $0.92) * 16 = $1.28
  Profit % = $0.80 / $1.28 = 62.5% → triggers sell at 30% threshold ✓

  Entry: BUY_NO on Fed Cut at YES=40% (NO=60%)  
  Fed holds rates, news breaks, YES drops to 5%, NO = 95%
  Current profit = ($0.95 - $0.60) * 25 = $8.75
  Max profit = ($1.00 - $0.60) * 25 = $10.00
  Profit % = 87.5% → triggers sell at 50% threshold ✓
  This is EXACTLY what happened the other night — we capture this now!
"""

import logging
import os
import time
import base64
import json
import uuid
import aiohttp
from typing import List, Dict, Tuple, Optional
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

log = logging.getLogger('profit_taker')

# Thresholds — configurable via Railway env vars
SPORTS_TAKE_PROFIT_PCT = float(os.getenv('SPORTS_TAKE_PROFIT_PCT', '0.30'))   # 30% of max profit
MACRO_TAKE_PROFIT_PCT  = float(os.getenv('MACRO_TAKE_PROFIT_PCT',  '0.50'))   # 50% of max profit
STOP_LOSS_PCT          = float(os.getenv('STOP_LOSS_PCT',           '0.50'))   # 50% of cost basis


def get_auth_headers(method, path):
    api_key = os.getenv('KALSHI_API_KEY')
    private_key_str = os.getenv('KALSHI_PRIVATE_KEY', '')
    timestamp = str(int(time.time() * 1000))
    message = timestamp + method.upper() + path.split('?')[0]
    key_str = private_key_str.strip().replace('\\n', '\n')
    try:
        private_key = serialization.load_pem_private_key(
            key_str.encode(), password=None, backend=default_backend()
        )
        sig = private_key.sign(
            message.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256.digest_size),
            hashes.SHA256()
        )
        return {
            'KALSHI-ACCESS-KEY': api_key,
            'KALSHI-ACCESS-SIGNATURE': base64.b64encode(sig).decode(),
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
        }
    except Exception as e:
        log.error(f"Auth error: {e}")
        return {}


class ProfitTaker:
    def __init__(self, config: Dict):
        self.dry_run = config.get('dry_run', True)
        self.session = None
        # {ticker: {side, entry_price, contracts, cost_basis, market_type}}
        self.entry_data = {}

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    def record_entry(self, ticker: str, side: str, entry_price: float,
                     contracts: float, cost_basis: float, market_type: str = 'sports'):
        """Record when a new position is opened."""
        self.entry_data[ticker] = {
            'side': side,
            'entry_price': entry_price,   # price of the side we bought (YES or NO)
            'contracts': contracts,
            'cost_basis': cost_basis,     # total dollars spent
            'market_type': market_type,
        }
        log.info(
            f"[PROFIT_TAKER] Tracking: {ticker} {side} "
            f"{contracts:.1f} contracts @ {entry_price:.2%} "
            f"cost=${cost_basis:.2f} type={market_type}"
        )

    async def load_existing_positions(self):
        """
        Pull entry data from Kalshi fills endpoint for positions
        opened before this module was deployed.
        """
        session = await self._get_session()
        path = '/trade-api/v2/portfolio/fills'
        headers = get_auth_headers('GET', path)
        url = f"https://api.elections.kalshi.com{path}?limit=100"
        try:
            async with session.get(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()

            # Build entry data from fills
            fills_by_ticker = {}
            for fill in data.get('fills', []):
                ticker = fill.get('ticker', '')
                action = fill.get('action', '')
                side = fill.get('side', '')
                count = float(fill.get('count', 0))
                yes_price = float(fill.get('yes_price', 0)) / 100  # cents to dollars

                if action != 'buy' or not ticker:
                    continue

                if ticker not in fills_by_ticker:
                    fills_by_ticker[ticker] = {'yes_buys': 0, 'no_buys': 0, 'yes_cost': 0, 'no_cost': 0}

                if side == 'yes':
                    fills_by_ticker[ticker]['yes_buys'] += count
                    fills_by_ticker[ticker]['yes_cost'] += count * yes_price
                elif side == 'no':
                    no_price = 1 - yes_price
                    fills_by_ticker[ticker]['no_buys'] += count
                    fills_by_ticker[ticker]['no_cost'] += count * no_price

            # Convert to entry_data format
            loaded = 0
            for ticker, fills in fills_by_ticker.items():
                if ticker in self.entry_data:
                    continue  # Already tracked

                if fills['yes_buys'] > 0 and fills['yes_cost'] > 0:
                    contracts = fills['yes_buys']
                    cost = fills['yes_cost']
                    entry_price = cost / contracts
                    self.entry_data[ticker] = {
                        'side': 'YES',
                        'entry_price': entry_price,
                        'contracts': contracts,
                        'cost_basis': cost,
                        'market_type': 'unknown',
                    }
                    loaded += 1
                elif fills['no_buys'] > 0 and fills['no_cost'] > 0:
                    contracts = fills['no_buys']
                    cost = fills['no_cost']
                    entry_price = cost / contracts
                    self.entry_data[ticker] = {
                        'side': 'NO',
                        'entry_price': entry_price,
                        'contracts': contracts,
                        'cost_basis': cost,
                        'market_type': 'unknown',
                    }
                    loaded += 1

            if loaded > 0:
                log.info(f"[PROFIT_TAKER] Loaded {loaded} existing positions from Kalshi fills")

        except Exception as e:
            log.debug(f"[PROFIT_TAKER] Could not load fills: {e}")

    async def fetch_current_price(self, ticker: str) -> Tuple[Optional[float], Optional[float]]:
        """Fetch current YES and NO mid-prices for a market."""
        session = await self._get_session()
        path = f'/trade-api/v2/markets/{ticker}'
        headers = get_auth_headers('GET', path)
        try:
            async with session.get(
                f"https://api.elections.kalshi.com{path}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status != 200:
                    return None, None
                data = await resp.json()
                market = data.get('market', {})
                yes_bid = float(market.get('yes_bid_dollars') or 0)
                yes_ask = float(market.get('yes_ask_dollars') or 0)
                if yes_bid > 0 and yes_ask > 0:
                    yes_price = (yes_bid + yes_ask) / 2
                elif yes_bid > 0:
                    yes_price = yes_bid
                elif yes_ask > 0:
                    yes_price = yes_ask
                else:
                    return None, None
                return yes_price, 1 - yes_price
        except Exception as e:
            log.debug(f"Price fetch error {ticker}: {e}")
            return None, None

    def _calculate_profit(self, entry: Dict, current_yes: float, current_no: float) -> Tuple[float, float, str]:
        """
        Returns (profit_dollars, profit_pct_of_max, description)
        profit_pct_of_max: positive = gain, negative = loss
        """
        side = entry['side']
        entry_price = entry['entry_price']  # price paid per contract for our side
        contracts = entry['contracts']
        cost_basis = entry['cost_basis']

        if side == 'YES':
            current_price = current_yes
        else:
            current_price = current_no

        current_value = current_price * contracts
        profit_dollars = current_value - cost_basis

        # Max possible profit = if position wins at $1 per contract
        max_profit = (1.0 - entry_price) * contracts

        if max_profit <= 0.01:  # essentially zero edge, skip
            return profit_dollars, 0.0, "no_max_profit"

        profit_pct = profit_dollars / max_profit
        desc = f"${profit_dollars:+.2f} ({profit_pct:+.0%} of max ${max_profit:.2f})"
        return profit_dollars, profit_pct, desc

    async def place_sell_order(self, ticker: str, side: str,
                                contracts: int, current_price: float) -> bool:
        """Execute a sell order to close a position."""
        if self.dry_run:
            log.info(
                f"[PROFIT_TAKER][DRY RUN] Would sell {side} "
                f"{contracts} contracts on {ticker} @ {current_price:.2%}"
            )
            return True

        session = await self._get_session()
        path = '/trade-api/v2/portfolio/orders'
        sell_side = 'yes' if side == 'YES' else 'no'

        order_payload = {
            'ticker': ticker,
            'client_order_id': str(uuid.uuid4()),
            'type': 'market',
            'action': 'sell',
            'side': sell_side,
            'count': int(contracts),
        }

        headers = get_auth_headers('POST', path)
        try:
            async with session.post(
                f"https://api.elections.kalshi.com{path}",
                headers=headers,
                data=json.dumps(order_payload),
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                result = await resp.json()
                if resp.status in (200, 201):
                    log.info(
                        f"[PROFIT_TAKER] ✓ SOLD {sell_side.upper()} "
                        f"{contracts} contracts on {ticker} @ {current_price:.2%}"
                    )
                    return True
                else:
                    log.error(f"[PROFIT_TAKER] Sell failed: {resp.status} {result}")
                    return False
        except Exception as e:
            log.error(f"[PROFIT_TAKER] Sell error: {e}")
            return False

    async def check_and_exit_positions(self, open_positions: Dict) -> List[Dict]:
        """
        Check all tracked positions. Exit if profit target or stop loss hit.
        Returns list of exits made this cycle.
        """
        # Load any existing positions we don't have entry data for
        await self.load_existing_positions()

        exits = []
        tickers = list(self.entry_data.keys())

        for ticker in tickers:
            # Skip if no longer in Kalshi open positions (already resolved/closed)
            if open_positions and ticker not in open_positions:
                if ticker in self.entry_data:
                    del self.entry_data[ticker]
                continue

            entry = self.entry_data.get(ticker)
            if not entry:
                continue

            current_yes, current_no = await self.fetch_current_price(ticker)
            if current_yes is None:
                continue

            profit_dollars, profit_pct, desc = self._calculate_profit(entry, current_yes, current_no)
            market_type = entry.get('market_type', 'sports')

            # Determine thresholds based on market type
            take_profit = MACRO_TAKE_PROFIT_PCT if market_type == 'macro' else SPORTS_TAKE_PROFIT_PCT
            stop_loss_threshold = -STOP_LOSS_PCT

            action = None
            if profit_pct >= take_profit:
                action = 'take_profit'
                log.info(
                    f"[PROFIT_TAKER] TAKE PROFIT: {ticker} {entry['side']} — "
                    f"{desc} (threshold: {take_profit:.0%})"
                )
            elif profit_pct <= stop_loss_threshold:
                action = 'stop_loss'
                log.info(
                    f"[PROFIT_TAKER] STOP LOSS: {ticker} {entry['side']} — "
                    f"{desc} (threshold: -{STOP_LOSS_PCT:.0%})"
                )

            if action:
                side = entry['side']
                contracts = max(1, int(entry['contracts']))
                exit_price = current_yes if side == 'YES' else current_no

                success = await self.place_sell_order(ticker, side, contracts, exit_price)
                if success:
                    exits.append({
                        'ticker': ticker,
                        'action': action,
                        'side': side,
                        'contracts': contracts,
                        'entry_price': entry['entry_price'],
                        'exit_price': exit_price,
                        'profit_dollars': profit_dollars,
                        'profit_pct': profit_pct,
                    })
                    del self.entry_data[ticker]

        if exits:
            log.info(f"[PROFIT_TAKER] Exited {len(exits)} positions this cycle")

        return exits

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
