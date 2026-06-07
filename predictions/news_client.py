"""
News client for MatchOracle Smart AI.
Fetches current football news from NewsAPI (if key is configured) and
falls back to DuckDuckGo web search snippets when no key is available.
All functions return empty lists gracefully on any failure.
"""
import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def _newsapi_key():
    return settings.MATCHORACLE.get('NEWSAPI_KEY', '')


def fetch_football_news(query, page_size=5):
    """
    Fetch current football news articles for a given query.

    Tries NewsAPI first (requires NEWSAPI_KEY env var).
    Falls back to DuckDuckGo search snippets if no key is set.

    Returns a list of article dicts:
      [{'title': str, 'description': str, 'url': str, 'published': str}, ...]
    """
    api_key = _newsapi_key()

    if api_key:
        return _fetch_from_newsapi(query, api_key, page_size)

    # Fallback: use DuckDuckGo snippets (already available via engine.search_web)
    return _fetch_from_duckduckgo(query, page_size)


def _fetch_from_newsapi(query, api_key, page_size):
    """Fetch articles from NewsAPI.org."""
    try:
        resp = requests.get(
            'https://newsapi.org/v2/everything',
            params={
                'q': query,
                'sortBy': 'publishedAt',
                'language': 'en',
                'pageSize': page_size,
                'apiKey': api_key,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            articles = resp.json().get('articles', [])
            return [
                {
                    'title': a.get('title', ''),
                    'description': a.get('description', '') or a.get('content', ''),
                    'url': a.get('url', ''),
                    'published': a.get('publishedAt', ''),
                    'source': a.get('source', {}).get('name', ''),
                }
                for a in articles
                if a.get('title') and '[Removed]' not in a.get('title', '')
            ]
        else:
            logger.warning(f"NewsAPI returned HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"NewsAPI fetch error: {e}")
    return []


def _fetch_from_duckduckgo(query, max_results):
    """
    Fallback: reuse the DuckDuckGo search already in engine.py and
    reformat results as news-style articles.
    """
    try:
        from predictions.engine import search_web
        results = search_web(f"{query} football news 2025", max_results=max_results)
        return [
            {
                'title': r.get('title', ''),
                'description': r.get('snippet', ''),
                'url': r.get('url', ''),
                'published': '',
                'source': 'Web Search',
            }
            for r in results
            if r.get('snippet')
        ]
    except Exception as e:
        logger.error(f"DuckDuckGo news fallback error: {e}")
    return []


def format_news_for_context(articles):
    """
    Convert a list of article dicts into a compact text string
    suitable for inclusion in an AI prompt context.
    """
    if not articles:
        return 'No recent news found.'
    lines = []
    for i, a in enumerate(articles[:5], 1):
        title = a.get('title', '')
        desc = a.get('description', '')
        pub = a.get('published', '')
        source = a.get('source', '')
        line = f"{i}. {title}"
        if desc:
            line += f" — {desc[:120]}"
        if pub:
            line += f" [{pub[:10]}]"
        if source:
            line += f" ({source})"
        lines.append(line)
    return '\n'.join(lines)
