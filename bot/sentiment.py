"""
News Sentiment Analyzer

Fetches breaking news and social sentiment signals that move
prediction market prices before they fully reprice.

Sources:
- Google News RSS (free, no API key needed)
- NewsAPI (already have key)
- Reddit via pushshift/old.reddit RSS (free)
- Financial news RSS feeds

Signals we look for:
- Breaking injury news on a team we're about to bet
- Surprise economic data leaks or previews
- Political announcements affecting macro markets
- Social media buzz on specific teams/players
"""

import logging
import aiohttp
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import List, Dict

log = logging.getLogger('sentiment')

# RSS feeds for breaking news
BREAKING_NEWS_FEEDS = {
    'ESPN Breaking': 'https://www.espn.com/espn/rss/news',
    'ESPN NBA': 'https://www.espn.com/espn/rss/nba/news',
    'ESPN Soccer': 'https://www.espn.com/espn/rss/soccer/news',
    'Sky Sports': 'https://www.skysports.com/rss/12040',
    'BBC Sport': 'https://feeds.bbci.co.uk/sport/rss.xml',
    'Reuters Sports': 'https://feeds.reuters.com/reuters/sportsNews',
    'AP Sports': 'https://rsshub.app/apnews/topics/sports',
    'Bleacher Report': 'https://bleacherreport.com/articles/feed',
}

MACRO_NEWS_FEEDS = {
    'Fed Reserve': 'https://www.federalreserve.gov/feeds/press_all.xml',
    'BLS': 'https://www.bls.gov/feed/bls_latest.rss',
    'Reuters Economy': 'https://feeds.reuters.com/reuters/businessNews',
    'WSJ Economy': 'https://feeds.a.dj.com/rss/RSSEconomics.xml',
    'Bloomberg Economics': 'https://feeds.bloomberg.com/economics/news.rss',
}

# Keywords that indicate HIGH URGENCY news
INJURY_KEYWORDS = [
    'injured', 'injury', 'out', 'doubtful', 'questionable', 'scratch',
    'ruled out', 'won\'t play', 'will not play', 'missed', 'absent',
    'suspended', 'suspension', 'banned', 'red card',
]

POSITIVE_KEYWORDS = [
    'returns', 'cleared', 'available', 'healthy', 'fit', 'starting',
    'back in', 'ready to play',
]

MACRO_KEYWORDS = [
    'fed', 'federal reserve', 'rate cut', 'rate hike', 'inflation',
    'cpi', 'jobs report', 'unemployment', 'recession', 'gdp',
    'fomc', 'powell', 'warsh',
]


class SentimentAnalyzer:
    def __init__(self):
        self.session = None
        self._cache = {}  # Simple cache to avoid re-fetching same feeds

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=8)
            )
        return self.session

    async def _fetch_rss(self, name: str, url: str) -> List[Dict]:
        session = await self._get_session()
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
            root = ET.fromstring(text)
            items = []
            for item in root.iter('item'):
                title = item.findtext('title', '').strip()
                desc = item.findtext('description', '').strip()[:200]
                pub_date = item.findtext('pubDate', '')[:25]
                link = item.findtext('link', '')
                if title:
                    items.append({
                        'source': name,
                        'title': title,
                        'description': desc,
                        'pub_date': pub_date,
                        'link': link,
                        'text': f"{title} {desc}".lower(),
                    })
                if len(items) >= 5:
                    break
            return items
        except:
            return []

    async def fetch_breaking_sports_news(self) -> List[str]:
        """Fetch latest sports news, highlight injuries."""
        tasks = [
            self._fetch_rss(name, url)
            for name, url in BREAKING_NEWS_FEEDS.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items = []
        for result in results:
            if isinstance(result, list):
                all_items.extend(result)

        # Deduplicate by title similarity
        seen_titles = set()
        unique_items = []
        for item in all_items:
            title_key = item['title'][:40].lower()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_items.append(item)

        # Format with urgency tags
        formatted = []
        for item in unique_items[:30]:
            text = item['text']
            urgency = ''

            # Check for injury keywords
            if any(kw in text for kw in INJURY_KEYWORDS):
                urgency = '🚨 INJURY: '
            elif any(kw in text for kw in POSITIVE_KEYWORDS):
                urgency = '✅ RETURN: '

            formatted.append(
                f"[{item['source']} | {item['pub_date'][:10]}] "
                f"{urgency}{item['title']}: {item['description'][:100]}"
            )

        return formatted

    async def fetch_macro_sentiment(self) -> List[str]:
        """Fetch macro/economic news sentiment."""
        tasks = [
            self._fetch_rss(name, url)
            for name, url in MACRO_NEWS_FEEDS.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items = []
        for result in results:
            if isinstance(result, list):
                all_items.extend(result)

        seen = set()
        formatted = []
        for item in all_items:
            key = item['title'][:40].lower()
            if key in seen:
                continue
            seen.add(key)

            text = item['text']
            if any(kw in text for kw in MACRO_KEYWORDS):
                formatted.append(
                    f"[{item['source']} | {item['pub_date'][:10]}] "
                    f"{item['title']}: {item['description'][:100]}"
                )
            if len(formatted) >= 15:
                break

        return formatted

    def check_team_in_news(self, team_name: str, news_items: List[str]) -> Dict:
        """
        Check if a specific team appears in recent news with injury context.
        Returns {'has_injury': bool, 'has_return': bool, 'relevant_items': list}
        """
        team_lower = team_name.lower()
        # Get main words from team name (skip common words)
        team_words = [
            w for w in team_lower.split()
            if len(w) > 3 and w not in {'city', 'united', 'real', 'club'}
        ]

        relevant = []
        has_injury = False
        has_return = False

        for item in news_items:
            item_lower = item.lower()
            # Check if team is mentioned
            if any(word in item_lower for word in team_words):
                relevant.append(item)
                if any(kw in item_lower for kw in INJURY_KEYWORDS):
                    has_injury = True
                if any(kw in item_lower for kw in POSITIVE_KEYWORDS):
                    has_return = True

        return {
            'has_injury': has_injury,
            'has_return': has_return,
            'relevant_items': relevant[:3],
        }

    async def get_full_context(self) -> Dict:
        """
        Fetch all sentiment data concurrently.
        Returns structured dict with sports and macro sentiment.
        """
        sports_task = self.fetch_breaking_sports_news()
        macro_task = self.fetch_macro_sentiment()

        sports_news, macro_news = await asyncio.gather(
            sports_task, macro_task, return_exceptions=True
        )

        if isinstance(sports_news, Exception):
            sports_news = []
        if isinstance(macro_news, Exception):
            macro_news = []

        log.info(
            f"[SENTIMENT] Fetched {len(sports_news)} sports + "
            f"{len(macro_news)} macro news items"
        )

        return {
            'sports': sports_news,
            'macro': macro_news,
            'all': sports_news + macro_news,
            'formatted': '\n'.join(sports_news[:20] + macro_news[:10]),
        }

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
