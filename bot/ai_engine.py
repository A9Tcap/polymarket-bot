"""
Expert AI Signal Engine — Politics & Economics Edition
Specialized in short-term macro, political, and economic event markets on Kalshi.
Uses real-time news, economic data, and institutional-grade analysis to find mispriced contracts.
"""

import logging
import asyncio
import os
import json
import aiohttp
from typing import List, Dict
from anthropic import AsyncAnthropic

log = logging.getLogger('ai_engine')

NEWS_API_BASE = "https://newsapi.org/v2"

# Key data sources for economic intelligence
ECONOMIC_CONTEXT = """
CURRENT MACRO ENVIRONMENT (as of March 2026):
- Federal Reserve: Rates held at 3.50-3.75% at March 18 meeting. Next FOMC: April 28-29, 2026.
- Fed Chair Powell emphasized patience. One rate cut expected for all of 2026.
- Inflation: CPI running ~2.4% YoY but likely higher (~2.7%) accounting for Oct 2025 data gap.
- Tariffs from Trump administration are primary upside inflation risk.
- US-Israel attacks on Iran began Feb 28 — energy prices rising, potential inflation shock.
- Core CPI sticky above 2% target. Fed in no rush to cut.
- Employment: Labor market showing some cracks but still resilient.
- S&P 500 volatile due to geopolitical risk and tariff uncertainty.
- Bitcoin and crypto markets elevated but volatile.
- Trump administration: active executive orders, policy uncertainty high.
"""

ANALYTICAL_FRAMEWORK = """
YOUR ANALYTICAL APPROACH:

For ECONOMIC markets (CPI, Fed rates, jobs, GDP):
1. Compare current market price to what hard data implies
2. Check if Bloomberg consensus aligns or diverges from market price
3. Consider upcoming data releases — are markets mispriced ahead of them?
4. Factor in current macro trends (tariffs, energy, Iran war impact on inflation)
5. The Fed is on hold — markets pricing in cuts are likely overpriced

For POLITICAL markets (executive orders, legislation, elections):
1. Check recent news for signals — Trump acts fast on stated priorities
2. Look at congressional calendar and political dynamics
3. Consider base rates — how often do similar things happen?
4. Factor in Trump's track record of following through on stated intentions

For CRYPTO markets:
1. Check current price momentum and market sentiment
2. Consider macro backdrop — risk-on vs risk-off environment
3. Look for specific catalysts (ETF flows, regulatory news, halving effects)

EDGE IDENTIFICATION:
- Market is overpriced when: crowd is too optimistic, ignoring base rates, or missing negative signals
- Market is underpriced when: crowd is too pessimistic, ignoring strong data, or missing positive catalysts
- Best opportunities: upcoming scheduled events (FOMC, CPI releases, votes) where you have information edge
"""


class AISignalEngine:
    def __init__(self):
        self.anthropic = AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        self.news_api_key = os.getenv('NEWS_API_KEY')
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_relevant_news(self, query: str, category: str = '') -> List[Dict]:
        """Fetch targeted news based on market question and category."""
        session = await self._get_session()
        try:
            # Build a targeted search query based on category
            if 'fed' in query.lower() or 'rate' in query.lower() or 'fomc' in query.lower():
                search_query = 'Federal Reserve interest rate policy 2026'
            elif 'cpi' in query.lower() or 'inflation' in query.lower():
                search_query = 'CPI inflation data 2026 tariffs'
            elif 'trump' in query.lower() or 'executive' in query.lower():
                search_query = 'Trump executive order policy 2026'
            elif 'bitcoin' in query.lower() or 'crypto' in query.lower():
                search_query = 'Bitcoin cryptocurrency price 2026'
            elif 'recession' in query.lower() or 'gdp' in query.lower():
                search_query = 'US GDP recession economy 2026'
            elif 'jobs' in query.lower() or 'unemployment' in query.lower():
                search_query = 'US jobs unemployment labor market 2026'
            else:
                search_query = query[:80]

            params = {
                'q': search_query,
                'sortBy': 'publishedAt',
                'pageSize': 8,
                'language': 'en',
                'apiKey': self.news_api_key,
            }
            async with session.get(f"{NEWS_API_BASE}/everything", params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                articles = data.get('articles', [])
                return [
                    {
                        'title': a.get('title', ''),
                        'description': a.get('description', ''),
                        'published': a.get('publishedAt', ''),
                        'source': a.get('source', {}).get('name', ''),
                    }
                    for a in articles[:8]
                ]
        except asyncio.TimeoutError:
            log.warning(f"AI analysis timed out for '{question[:50]}'")
            return None
        except Exception as e:
            log.warning(f"News fetch error: {e}")
            return []

    async def analyze_single_market(self, market: Dict) -> Dict:
        """
        Deep expert analysis of a single politics/economics market.
        Uses macro context, live news, and institutional-grade reasoning.
        """
        question = market['question']
        yes_price = market['yes_price']
        category = market.get('category', '')
        end_date = market.get('end_date', 'unknown')

        # Fetch targeted news
        news = await self.get_relevant_news(question, category)
        news_text = "\n".join([
            f"- [{a['source']} | {a['published'][:10]}] {a['title']}: {a['description']}"
            for a in news if a['title']
        ]) or "No recent news found."

        prompt = f"""You are the world's most sophisticated prediction market analyst, combining the expertise of a senior Fed economist, a political strategist, and a quantitative trader. Your edge comes from synthesizing hard data, news flow, and base rates to find mispriced contracts.

MARKET QUESTION: {question}
CATEGORY: {category}
RESOLUTION DATE: {end_date}
CURRENT YES PRICE: {yes_price:.2%} (market's implied probability YES resolves)
CURRENT NO PRICE: {1-yes_price:.2%}

{ECONOMIC_CONTEXT}

{ANALYTICAL_FRAMEWORK}

RECENT RELEVANT NEWS:
{news_text}

YOUR TASK:
Analyze this market with institutional-grade rigor. Think step by step:

1. WHAT IS BEING ASKED: Precisely what needs to happen for YES to resolve?
2. BASE RATE: Historically, how often does this type of event occur?
3. CURRENT SIGNALS: What do recent news, data, and trends tell us?
4. MARKET PRICE ASSESSMENT: Is {yes_price:.2%} fair, too high, or too low?
5. EDGE: What specific information or reasoning gives you conviction?
6. RISKS: What could make you wrong?

Only recommend a trade if you have GENUINE ANALYTICAL EDGE — not just a guess.
Be highly selective. Most markets are fairly priced. SKIP unless you see clear mispricing.

Respond ONLY with valid JSON:
{{
  "true_probability_yes": 0.65,
  "market_price_yes": {yes_price:.4f},
  "edge": 0.12,
  "direction": "BUY_YES",
  "confidence": "HIGH",
  "reasoning": "Specific 2-3 sentence explanation citing actual data points or signals",
  "key_risk": "One sentence on main risk to this view",
  "signal": true
}}

Rules:
- edge must be POSITIVE and represent abs(true_probability - market_price)
- Only set signal=true if edge >= 0.06 AND confidence is HIGH
- direction must be BUY_YES, BUY_NO, or SKIP
- Be brutally honest — SKIP is the right answer most of the time
- Never manufacture conviction — only bet when the edge is real and specific"""

        try:
            response = await asyncio.wait_for(
                self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            ), timeout=30
            )
            raw = response.content[0].text.strip()
            raw = raw.replace('```json', '').replace('```', '').strip()

            start = raw.find('{')
            end = raw.rfind('}') + 1
            if start == -1 or end == 0:
                return None
            raw = raw[start:end]

            analysis = json.loads(raw)

            edge = abs(float(analysis.get('edge', 0)))
            direction = analysis.get('direction', 'SKIP')
            signal = analysis.get('signal', False)
            confidence = analysis.get('confidence', 'LOW')

            # Higher bar for this strategy — require 6% edge and HIGH confidence
            if signal and direction != 'SKIP' and edge >= 0.06 and confidence == 'HIGH':
                true_prob = float(analysis.get('true_probability_yes', yes_price))
                return {
                    'type': 'ai_signal',
                    'market': market,
                    'direction': direction,
                    'true_probability': true_prob,
                    'market_price': yes_price,
                    'edge': edge,
                    'confidence': confidence,
                    'reasoning': analysis.get('reasoning', ''),
                    'key_risk': analysis.get('key_risk', ''),
                    'expected_value': edge * min(true_prob, 1 - true_prob),
                    'source': 'ai_engine',
                }

        except asyncio.TimeoutError:
            log.warning(f"AI analysis timed out for '{question[:50]}'")
            return None
        except Exception as e:
            log.warning(f"AI analysis failed for '{question[:50]}': {e}")

        return None

    async def analyze_markets(self, markets: List[Dict]) -> List[Dict]:
        """Analyze a batch of markets and return only high-conviction signals."""
        signals = []

        # Focus on markets with meaningful probability ranges
        candidates = [
            m for m in markets
            if 0.10 <= m['yes_price'] <= 0.90
        ]

        log.info(f"Analyzing {min(len(candidates), 20)} candidate markets with expert AI...")

        for market in candidates[:20]:
            signal = await self.analyze_single_market(market)
            if signal:
                signals.append(signal)
                log.info(
                    f"Signal: {signal['direction']} '{market['question'][:60]}' "
                    f"edge={signal['edge']:.2%} conf={signal['confidence']} | {signal['reasoning'][:80]}"
                )

        return signals

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
