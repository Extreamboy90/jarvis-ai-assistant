"""
Web Search plugin - Search the web using Google (primary) and DuckDuckGo (fallback)
"""

from plugins import function
import requests
from typing import List, Dict
import logging
import json
import random
import time

logger = logging.getLogger(__name__)

# User agents pool for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False
    logger.warning("duckduckgo-search library not available, using fallback method")

def _search_google(query: str, max_results: int = 5) -> List[Dict]:
    """
    Search Google and parse results

    Args:
        query: Search query
        max_results: Max results to return

    Returns:
        List of search results
    """
    results = []

    try:
        from bs4 import BeautifulSoup
        from urllib.parse import quote_plus

        # Random User-Agent
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

        # Google search URL
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&num={max_results+5}&hl=it"

        # Small delay to avoid rate limiting
        time.sleep(random.uniform(0.5, 1.5))

        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find search result divs - Google uses multiple possible classes
        search_divs = soup.find_all('div', class_='g') or \
                      soup.find_all('div', {'data-sokoban-container': True}) or \
                      soup.find_all('div', class_='Gx5Zad')

        # Alternative: find all links and filter
        if not search_divs:
            all_links = soup.find_all('a', href=True)
            # Filter for real result links (not navigation, etc)
            for link in all_links[:max_results*2]:
                href = link.get('href', '')
                if '/url?q=' in href or (href.startswith('http') and 'google.com' not in href):
                    h3 = link.find('h3')
                    if h3:
                        search_divs.append(link.parent.parent if link.parent else link)

        for div in search_divs[:max_results]:
            try:
                # Title and URL
                title_tag = div.find('h3')
                link_tag = div.find('a')

                if not title_tag or not link_tag:
                    continue

                title = title_tag.get_text(strip=True)
                url = link_tag.get('href', '')

                # Clean URL (Google wraps with /url?q=)
                if url.startswith('/url?q='):
                    url = url.split('/url?q=')[1].split('&')[0]

                # Skip non-http URLs
                if not url.startswith('http'):
                    continue

                # Snippet
                snippet_div = div.find('div', class_=['VwiC3b', 'IsZvec', 'lEBKkf'])
                snippet = snippet_div.get_text(strip=True) if snippet_div else ""

                # Extract domain
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc
                except:
                    domain = url.split('/')[2] if len(url.split('/')) > 2 else "Web"

                results.append({
                    "title": title[:200],
                    "snippet": snippet[:500],
                    "url": url,
                    "source": domain
                })

            except Exception as e:
                logger.debug(f"Error parsing Google result: {e}")
                continue

        logger.info(f"Found {len(results)} results from Google")

    except Exception as e:
        logger.error(f"Google search error: {e}")

    return results


@function(
    name="search_web",
    description="Search the web for information using Google. Automatically fetches and extracts content from top results.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 5)",
                "default": 5
            },
            "fetch_content": {
                "type": "boolean",
                "description": "Automatically fetch page content for top 2 results (default: true)",
                "default": True
            }
        },
        "required": ["query"]
    }
)
def search_web(query: str, max_results: int = 5, fetch_content: bool = True) -> Dict:
    """
    Search the web using DuckDuckGo

    Args:
        query: Search query string
        max_results: Maximum number of results to return
        fetch_content: Whether to fetch page content

    Returns:
        Dictionary with search results
    """
    try:
        # Ensure max_results is int (Gemini sometimes sends float)
        max_results = int(max_results)

        results = []

        # Try Google first
        logger.info(f"Searching Google for: {query}")
        results = _search_google(query, max_results)

        # Fallback to DuckDuckGo if Google fails
        if not results:
            logger.warning("Google search failed, trying DuckDuckGo fallback")
            try:
                from bs4 import BeautifulSoup
                from urllib.parse import quote_plus

                headers = {"User-Agent": random.choice(USER_AGENTS)}
                search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

                time.sleep(random.uniform(0.3, 0.8))

                response = requests.get(search_url, headers=headers, timeout=10)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')
                result_divs = soup.find_all('div', class_='result')

                for div in result_divs[:max_results]:
                    try:
                        title_tag = div.find('a', class_='result__a')
                        snippet_tag = div.find('a', class_='result__snippet')

                        if title_tag:
                            title = title_tag.get_text(strip=True)
                            url = title_tag.get('href', '')
                            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

                            # DuckDuckGo wraps URLs - extract real domain
                            from urllib.parse import urlparse, parse_qs, unquote
                            real_url = url
                            if 'duckduckgo.com/l/' in url:
                                try:
                                    parsed = parse_qs(urlparse(url).query)
                                    if 'uddg' in parsed:
                                        real_url = unquote(parsed['uddg'][0])
                                except:
                                    pass

                            # Extract domain
                            try:
                                domain = urlparse(real_url).netloc
                            except:
                                domain = real_url.split('/')[2] if real_url.startswith('http') and len(real_url.split('/')) > 2 else "Web"

                            results.append({
                                "title": title[:200],
                                "snippet": snippet[:500],
                                "url": real_url,
                                "source": domain
                            })
                    except Exception as e:
                        logger.debug(f"Error parsing DuckDuckGo result: {e}")
                        continue

                logger.info(f"Found {len(results)} results from DuckDuckGo")

            except Exception as e:
                logger.error(f"DuckDuckGo fallback error: {e}")

        # Last resort: instant answer API
        if not results:
            logger.warning(f"All search methods failed, trying instant answer API for query: {query}")
            results = _try_instant_answer_api(query, max_results)

        # Fetch content from top results if requested
        if fetch_content and results:
            num_to_fetch = min(2, len(results))  # Fetch top 2 results
            logger.info(f"Fetching content from top {num_to_fetch} results")

            for i in range(num_to_fetch):
                url = results[i].get('url')
                if url and url.startswith('http'):
                    try:
                        content_result = get_web_content(url)
                        if content_result.get('success'):
                            results[i]['full_content'] = content_result.get('content', '')[:1500]  # Limit to 1500 chars
                            logger.info(f"Successfully fetched content from {url}")
                        else:
                            logger.warning(f"Failed to fetch content from {url}: {content_result.get('error')}")
                    except Exception as e:
                        logger.error(f"Error fetching content from {url}: {e}")

        return {
            "success": True,
            "query": query,
            "results": results,
            "total_results": len(results),
            "content_fetched": fetch_content
        }

    except Exception as e:
        logger.error(f"Unexpected error in web search: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


def _parse_duckduckgo_html(html: str, max_results: int) -> List[Dict]:
    """
    Parse DuckDuckGo HTML search results
    """
    results = []
    try:
        import re

        # Find all result blocks (simple regex parsing)
        # DuckDuckGo HTML structure: <div class="result__body">
        result_pattern = r'<a class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?<a class="result__snippet"[^>]*>(.*?)</a>'
        matches = re.findall(result_pattern, html, re.DOTALL)

        for match in matches[:max_results]:
            url = match[0]
            title = re.sub(r'<[^>]+>', '', match[1]).strip()
            snippet = re.sub(r'<[^>]+>', '', match[2]).strip()

            # Clean up HTML entities
            title = title.replace('&quot;', '"').replace('&amp;', '&').replace('&#x27;', "'")
            snippet = snippet.replace('&quot;', '"').replace('&amp;', '&').replace('&#x27;', "'")

            # Extract domain from URL
            domain = re.search(r'https?://([^/]+)', url)
            source = domain.group(1) if domain else "Web"

            results.append({
                "title": title[:200] if title else "Result",
                "snippet": snippet[:500] if snippet else "",
                "url": url,
                "source": source
            })

    except Exception as e:
        logger.error(f"Error parsing DuckDuckGo HTML: {e}")

    return results


def _try_instant_answer_api(query: str, max_results: int) -> List[Dict]:
    """
    Fallback to DuckDuckGo Instant Answer API
    """
    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        results = []

        # Abstract (main answer)
        if data.get("Abstract"):
            results.append({
                "title": data.get("Heading", "Answer"),
                "snippet": data.get("Abstract"),
                "url": data.get("AbstractURL", ""),
                "source": data.get("AbstractSource", "DuckDuckGo")
            })

        # Related Topics
        for topic in data.get("RelatedTopics", [])[:max_results-1]:
            if isinstance(topic, dict) and "Text" in topic:
                results.append({
                    "title": topic.get("Text", "").split(" - ")[0] if " - " in topic.get("Text", "") else "Related",
                    "snippet": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                    "source": "DuckDuckGo"
                })

        return results

    except Exception as e:
        logger.error(f"Instant Answer API error: {e}")
        return []


@function(
    name="get_weather_forecast",
    description="Get current weather forecast for a specific location",
    parameters={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City name or location (e.g. 'Rome', 'Milan', 'Cagliari')"
            }
        },
        "required": ["location"]
    }
)
def get_weather_forecast(location: str) -> Dict:
    """
    Get weather forecast using OpenWeatherMap API or fallback to web search

    This function is used by the Mission Control dashboard for daily briefings.
    Requires OPENWEATHER_API_KEY environment variable.
    """
    import os

    try:
        api_key = os.getenv("OPENWEATHER_API_KEY")

        if not api_key:
            logger.warning("OPENWEATHER_API_KEY not set, falling back to web search")
            # Fallback: search web for weather
            search_result = search_web(f"meteo {location} oggi", max_results=3, fetch_content=False)

            if search_result.get("success") and search_result.get("results"):
                return {
                    "success": True,
                    "location": location,
                    "source": "web_search",
                    "data": search_result["results"][:2],
                    "note": "Weather data from web search (OpenWeatherMap API not configured)"
                }
            else:
                return {
                    "success": False,
                    "error": "Weather API not configured and web search failed",
                    "location": location
                }

        # Use OpenWeatherMap API
        url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": location,
            "appid": api_key,
            "units": "metric",
            "lang": "it"
        }

        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        # Format response
        weather_info = {
            "success": True,
            "location": data.get("name", location),
            "country": data.get("sys", {}).get("country", ""),
            "temperature": round(data["main"]["temp"]),
            "feels_like": round(data["main"]["feels_like"]),
            "temp_min": round(data["main"]["temp_min"]),
            "temp_max": round(data["main"]["temp_max"]),
            "description": data["weather"][0]["description"],
            "humidity": data["main"]["humidity"],
            "pressure": data["main"]["pressure"],
            "wind_speed": round(data["wind"]["speed"] * 3.6, 1),  # m/s to km/h
            "clouds": data["clouds"]["all"],
            "icon": data["weather"][0]["icon"],
            "sunrise": data["sys"].get("sunrise"),
            "sunset": data["sys"].get("sunset"),
            "source": "openweathermap"
        }

        logger.info(f"Weather fetched for {location}: {weather_info['temperature']}°C, {weather_info['description']}")

        return weather_info

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return {
                "success": False,
                "error": f"Location '{location}' not found",
                "location": location
            }
        else:
            return {
                "success": False,
                "error": f"Weather API error: {str(e)}",
                "location": location
            }
    except Exception as e:
        logger.error(f"Error getting weather for {location}: {e}")
        return {
            "success": False,
            "error": f"Weather fetch error: {str(e)}",
            "location": location
        }


@function(
    name="get_web_content",
    description="Fetch and extract text content from a specific URL",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch content from"
            }
        },
        "required": ["url"]
    }
)
def get_web_content(url: str) -> Dict:
    """
    Fetch content from a URL and return cleaned text

    Args:
        url: The URL to fetch

    Returns:
        Dictionary with page content
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        response.raise_for_status()

        # Try BeautifulSoup for better extraction
        try:
            from bs4 import BeautifulSoup
            import re as regex_module
            soup = BeautifulSoup(response.text, 'html.parser')

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
                script.decompose()

            # Get main content - try common content tags first
            main_content = soup.find('main') or soup.find('article') or soup.find('div', class_=regex_module.compile(r'content|article|post'))

            if main_content:
                text = main_content.get_text(separator=' ', strip=True)
            else:
                text = soup.get_text(separator=' ', strip=True)

            # Clean up whitespace
            text = regex_module.sub(r'\s+', ' ', text).strip()

        except (ImportError, Exception) as e:
            # Fallback to basic regex cleaning
            logger.debug(f"BeautifulSoup extraction failed, using regex fallback: {e}")
            import re as regex_module
            content = response.text
            text = regex_module.sub(r'<script[^>]*>.*?</script>', '', content, flags=regex_module.DOTALL)
            text = regex_module.sub(r'<style[^>]*>.*?</style>', '', text, flags=regex_module.DOTALL)
            text = regex_module.sub(r'<[^>]+>', ' ', text)
            text = regex_module.sub(r'\s+', ' ', text).strip()

        # Limit length
        max_length = 3000
        if len(text) > max_length:
            text = text[:max_length] + "..."

        return {
            "success": True,
            "url": url,
            "content": text,
            "length": len(text)
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Request timed out"
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"Failed to fetch URL: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error fetching web content: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }
