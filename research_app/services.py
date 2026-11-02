import os
import re
import requests
import time
import trafilatura
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv()

TIMEOUT = 40

TAVILY_URL = "https://api.tavily.com/search"
ARXIV_URL = "https://export.arxiv.org/api/query"
GITHUB_URL = "https://api.github.com/search/repositories"



# EXTRACT ARTICLE TEXT
def extract_article_text(url):
    """Extract clean article text and create a short description."""

    try:
        response = requests.get(
            url,
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0"},
        )

        if not response.ok:
            return None

        article_text = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            deduplicate=True,
            output_format="txt",
        )

        if not article_text:
            return None

        # Normalize whitespace.
        article_text = re.sub(r"\s+", " ", article_text).strip()

        # Remove common website navigation and promotional phrases.
        unwanted_phrases = [
            "related articles",
            "related posts",
            "you may also like",
            "read more articles",
            "subscribe to our newsletter",
            "skip to content",
            "sign in",
            "log in",
            "table of contents",
            "share this article",
            "cookie policy",
            "privacy policy",
            "terms of use",
        ]

        # Split the extracted text into sentences.
        sentences = re.split(
            r"(?<=[.!?])\s+",
            article_text,
        )

        cleaned_sentences = []

        for sentence in sentences:
            sentence = sentence.strip()

            # Ignore very short fragments.
            if len(sentence.split()) < 8:
                continue

            sentence_lower = sentence.lower()

            # Ignore navigation, promotional and related-article text.
            if any(
                phrase in sentence_lower
                for phrase in unwanted_phrases
            ):
                continue

            # Ignore sentences that look like website navigation.
            if sentence_lower.startswith(
                ("home |", "home >", "menu ", "tags:", "share:")
            ):
                continue

            cleaned_sentences.append(sentence)

        if not cleaned_sentences:
            return None

        # Use the first few readable sentences.
        summary = " ".join(cleaned_sentences[:4]).strip()

        # Keep the description within the intended length.
        if len(summary) > 900:
            summary = summary[:900].rsplit(" ", 1)[0].rstrip(" ,;:-")

        return summary or None

    except requests.RequestException as error:
        print(f"Article extraction failed for {url}: {error}")
        return None

    except Exception as error:
        print(f"Article extraction failed for {url}: {error}")
        return None


# SEARCH TAVILY
def search_tavily(query):
    """Fetch, filter, clean, and rank recent embedded technology news."""

    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        return [], "Tavily API key not found. Check your .env file."

    technology_query = (
        f"{query} recent industry news, company announcements, "
        "new hardware launches, semiconductor news, processor releases, "
        "firmware updates, robotics developments, embedded Linux, "
        "microcontrollers, RTOS and edge AI"
    )

    excluded_url_terms = [
        "bsky.social",
        "bluesky",
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "x.com/",
        "twitter.com",
        "youtube.com",
        "reddit.com",
    ]

    excluded_title_phrases = [
        # Tutorials and educational guides
        "what is ",
        "what are ",
        "beginner's guide",
        "beginners guide",
        "tutorial",
        "definition of ",
        "introduction to ",
        "complete guide to",
        "ultimate guide",
        "how to ",
        "learn embedded",
        "programming languages to learn",
        "open-source hardware guide",

        # Product reviews
        "review:",
        "review -",
        "review of ",
        "hands-on review",
        "first look",
        "product review",
        "board review",

        # Market reports and forecasts
        "market size",
        "market share",
        "market growth",
        "growth report",
        "market forecast",
        "industry forecast",
        "market 2026",
        "trends and forecast",
        "forecast to",
        "market outlook",
        "market analysis",
        "market research",
        "market report",
        "market advances",
        "market to reach",
        "cagr",
        "by 2030",
        "by 2035",

        # Press-release labels
        "press release:",
    ]

    technology_keywords = [
        "embedded",
        "firmware",
        "microcontroller",
        "microprocessor",
        "robotics",
        "robot",
        "electronics",
        "semiconductor",
        "risc-v",
        "arm",
        "iot",
        "rtos",
        "edge computing",
        "sensor",
        "fpga",
        "hardware",
        "chip",
        "zephyr",
        "freertos",
        "processor",
        "pcb",
        "embedded linux",
    ]

    development_keywords = [
        "announces",
        "announced",
        "launches",
        "launched",
        "introduces",
        "introduced",
        "unveils",
        "unveiled",
        "releases",
        "released",
        "partnership",
        "acquisition",
        "production",
        "breakthrough",
        "funding",
        "new product",
        "validates",
        "integrates",
        "expands",
        "develops",
        "ships",
        "deployed",
        "demonstrates",
    ]

    excluded_description_phrases = [
        "skip to content",
        "view all results",
        "subscribe to our newsletter",
        "subscribe now",
        "sign in",
        "log in",
        "share this article",
        "related articles",
        "related posts",
        "you may also like",
        "on this page",
    ]

    product_page_terms = [
        "/products/",
        "/product/",
        "/product-detail",
        "/product-details",
        "/datasheet",
        "/data-sheet",
    ]

    query_words = [
        word.lower()
        for word in re.findall(r"[a-zA-Z0-9+-]+", query)
        if len(word) >= 4
    ]

    start_time = time.time()

    try:
        response = requests.post(
            TAVILY_URL,
            json={
                "api_key": api_key,
                "query": technology_query,
                "topic": "news",
                "time_range": "month",
                "search_depth": "advanced",
                "max_results": 15,
                "include_answer": False,
            },
            timeout=TIMEOUT,
        )

        response.raise_for_status()

        items = response.json().get("results", [])

        ranked_results = []
        seen_urls = set()

        for item in items:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            description = (item.get("content") or "").strip()
            published_date = item.get("published_date") or ""

            # Skip incomplete results.
            if not title or not url or not published_date:
                continue

            title_lower = title.lower()
            url_lower = url.lower()

            # Exclude social media pages.
            if any(term in url_lower for term in excluded_url_terms):
                continue

            # Exclude product catalogues and specification pages.
            if any(term in url_lower for term in product_page_terms):
                continue

            # Exclude tutorials, reviews, and market reports.
            if any(
                phrase in title_lower
                for phrase in excluded_title_phrases
            ):
                continue

            # Parse ISO dates first, then try standard email-style dates.
            try:
                try:
                    article_date = datetime.fromisoformat(
                        published_date.replace("Z", "+00:00")
                    )
                except ValueError:
                    article_date = parsedate_to_datetime(published_date)

                if article_date.tzinfo is None:
                    article_date = article_date.replace(
                        tzinfo=timezone.utc
                    )

                age = datetime.now(timezone.utc) - article_date

                # Reject future dates and articles older than 30 days.
                if age < timedelta(0) or age > timedelta(days=30):
                    continue

            except (ValueError, TypeError, OverflowError):
                # Skip results whose publication date cannot be verified.
                continue

            # Normalize URLs to prevent duplicate articles.
            normalized_url = url.split("#", 1)[0].rstrip("/").lower()

            if normalized_url in seen_urls:
                continue

            # Remove common navigation and promotional text.
            for phrase in excluded_description_phrases:
                description = re.sub(
                    re.escape(phrase),
                    "",
                    description,
                    flags=re.IGNORECASE,
                )

            description = re.sub(
                r"\b(?:tags|share|prev|previous|next|bookmark)\b\s*:?",
                "",
                description,
                flags=re.IGNORECASE,
            )

            # Normalize whitespace and leftover separators.
            description = re.sub(
                r"\s+",
                " ",
                description,
            ).strip(" \t\n\r|#-")

            # Limit descriptions to a readable length.
            if len(description) > 700:
                description = (
                    description[:700].rsplit(" ", 1)[0].rstrip()
                    + "..."
                )

            # Evaluate relevance using both the title and description.
            title_and_description = f"{title} {description}".lower()

            technology_matches = sum(
                1
                for keyword in technology_keywords
                if keyword in title_and_description
            )

            query_matches = sum(
                1
                for word in query_words
                if word in title_and_description
            )

            # Reject results with no identifiable technology relevance.
            if technology_matches == 0 and query_matches == 0:
                continue

            # Give greater importance to query matches in the title.
            title_query_matches = sum(
                1
                for word in query_words
                if word in title_lower
            )

            development_matches = sum(
                1
                for keyword in development_keywords
                if keyword in title_lower
            )

            score = (
                technology_matches * 2
                + query_matches * 2
                + title_query_matches * 3
                + development_matches * 2
            )

            seen_urls.add(normalized_url)

            ranked_results.append({
                "title": title,
                "url": url,
                "description": description,
                "published_date": published_date,
                "source": "Industry News & Articles",
                "_score": score,
            })

        # Display the highest-ranked results first.
        ranked_results.sort(
            key=lambda result: result["_score"],
            reverse=True,
        )

        # Remove the internal score before returning results to Django.
        results = []

        for item in ranked_results:
            item.pop("_score", None)
            results.append(item)

        elapsed_time = time.time() - start_time

        print(
            f"Tavily search completed in {elapsed_time:.2f} seconds; "
            f"{len(results)} articles returned."
        )

        return results, None

    except requests.Timeout as error:
        print(f"Tavily request timed out: {error}")

        return [], (
            "Tavily took too long to respond. "
            "Please try searching again."
        )

    except requests.RequestException as error:
        print(f"Tavily request failed: {error}")

        return [], (
            "Tavily could not retrieve results. "
            "Please check your internet connection and API access."
        )

    except (ValueError, TypeError) as error:
        print(f"Tavily returned an unexpected response: {error}")

        return [], "Tavily returned an unexpected response."


# SEARCH ARXIV
def search_arxiv(query):
    """Search recent academic research papers on arXiv."""

    try:
        # Use broad technology topics when the search box is empty.
        if not query or not query.strip():
            terms = [
                "embedded systems",
                "robotics",
                "microcontrollers",
                "embedded Linux",
                "firmware",
            ]
        else:
            # Split user-provided topics separated by commas or semicolons.
            terms = [
                term.strip()
                for term in re.split(r"[,;]", query.strip())
                if term.strip()
            ]

        if not terms:
            return [], None

        # Search for papers submitted within the last 30 days.
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=30)

        date_filter = (
            f"submittedDate:[{start_date.strftime('%Y%m%d')}0000 "
            f"TO {end_date.strftime('%Y%m%d')}2359]"
        )

        # Build an arXiv search query for each topic.
        term_queries = []

        for term in terms[:5]:
            safe_term = term.replace('"', "").strip()

            if safe_term:
                term_queries.append(f'all:"{safe_term}"')

        if not term_queries:
            return [], None

        combined_query = " OR ".join(term_queries)

        print("arXiv search query:", combined_query)
        print("arXiv date range:", start_date, "to", end_date)

        response = requests.get(
            ARXIV_URL,
            params={
                "search_query": f"({combined_query}) AND {date_filter}",
                "start": 0,
                "max_results": 30,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            },
            timeout=TIMEOUT,
        )

        response.raise_for_status()

        root = ET.fromstring(response.content)

        namespace = {
            "atom": "http://www.w3.org/2005/Atom"
        }

        entries = root.findall("atom:entry", namespace)

        print("arXiv entries returned:", len(entries))

        results = []

        for entry in entries:
            title = entry.findtext(
                "atom:title", "", namespace
            ).strip()

            summary = entry.findtext(
                "atom:summary", "", namespace
            ).strip()

            link = entry.findtext(
                "atom:id", "", namespace
            ).strip()

            published = entry.findtext(
                "atom:published", "", namespace
            ).strip()

            if not title or not link or not published:
                continue

            try:
                published_date = datetime.fromisoformat(
                    published.replace("Z", "+00:00")
                ).date()
            except ValueError:
                continue

            if not start_date <= published_date <= end_date:
                continue

            results.append({
                "title": " ".join(title.split()),
                "url": link,
                "description": " ".join(summary.split()),
                "published_date": published_date.strftime("%b %d, %Y"),
                "source": "arXiv Research Paper",
            })

        return results, None

    except requests.RequestException as error:
        print("arXiv API error:", error)
        return [], "arXiv is temporarily unavailable."

    except (ET.ParseError, ValueError, TypeError) as error:
        print("arXiv processing error:", error)
        return [], "Could not process the arXiv response."


# SEARCH GITHUB
def search_github(query):
    """Find relevant GitHub repositories with one authenticated API request."""

    try:
        relevant_keywords = [
            "embedded", "firmware", "microcontroller",
            "esp32", "stm32", "risc-v", "arduino",
            "raspberry pi", "freertos", "rtos", "zephyr",
            "micropython", "robotics", "robot", "fpga",
            "device driver", "bare-metal", "hardware",
            "electronics", "iot", "sensor", "edge computing",
        ]

        # Use a broad default query on the homepage.
        search_term = query.strip() or "embedded"

        # Read the optional GitHub token from .env.
        github_token = os.getenv("GITHUB_TOKEN", "").strip()

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        response = requests.get(
            "https://api.github.com/search/repositories",
            params={
                "q": search_term,
                "sort": "stars",
                "order": "desc",
                "per_page": 10,
            },
            headers=headers,
            timeout=TIMEOUT,
        )

        # Handle rate-limit errors without retrying repeatedly.
        if response.status_code == 403:
            message = response.json().get("message", "Access denied")

            if (
                "rate limit" in message.lower()
                or response.headers.get("X-RateLimit-Remaining") == "0"
            ):
                reset_time = response.headers.get("X-RateLimit-Reset")
                print("GitHub rate limit reached. Reset timestamp:", reset_time)

                return [], (
                    "GitHub API rate limit reached. "
                    "Please wait for the limit to reset."
                )

        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])

        print("GITHUB SEARCH QUERY:", search_term)
        print("GITHUB STATUS:", response.status_code)
        print("GITHUB RAW REPOSITORY COUNT:", len(items))

        repositories = {}

        query_words = [
            word.lower()
            for word in search_term.split()
            if len(word) > 2
        ]

        for item in items:
            repo_name = item.get("name", "")
            owner = item.get("owner", {}).get("login", "")
            description = item.get("description") or ""

            # Create a concise, readable project heading.
            name_parts = repo_name.replace("-", " ").replace("_", " ").strip()
            title = name_parts.title() if name_parts else repo_name

            # Add a short category based on the actual repository description.
            description_lower = description.lower()

            if any(word in description_lower for word in [
                "speech-to-text", "speech recognition", "voice recognition"
            ]):
                title = f"{title} — Speech Recognition"

            elif any(word in description_lower for word in [
                "embedded ui", "graphics library", "microcontroller graphics"
            ]):
                title = f"{title} — Embedded Graphics"

            elif any(word in description_lower for word in [
                "business intelligence", "embedded analytics"
            ]):
                title = f"{title} — Embedded Analytics"

            elif any(word in description_lower for word in [
                "cross-platform", "webassembly"
            ]):
                title = f"{title} — Cross-Platform Framework"

            # Keep the original description for filtering and scoring.
            text_to_check = f"{owner}/{repo_name} {description}".lower()

            matched_keywords = [
                keyword
                for keyword in relevant_keywords
                if keyword in text_to_check
            ]

            # Ignore unrelated repositories.
            if not matched_keywords:
                continue

            url = item.get("html_url")
            if not url:
                continue

            score = sum(
                5 if keyword in repo_name.lower() else 3
                for keyword in matched_keywords
            )

            score += sum(
                2 for word in query_words
                if word in text_to_check
            )

            repositories[url] = {
                "score": score,
                "stars": item.get("stargazers_count", 0),
                "result": {
                    "title": title,
                    "url": url,
                    "description": (
                        description or "No description available."
                    ),
                    "source": "GitHub Repository",
                },
            }

        ranked = sorted(
            repositories.values(),
            key=lambda item: (item["score"], item["stars"]),
            reverse=True,
        )

        results = [
            item["result"]
            for item in ranked[:10]
        ]

        print("GITHUB RELEVANT PROJECTS:", len(results))

        return results, None

    except requests.RequestException as exc:
        print("GITHUB API ERROR:", exc)
        return [], f"GitHub search failed: {exc}"



def remove_duplicates(results):
    """Remove duplicate results by URL while preserving order."""
    unique_results = []
    seen_urls = set()

    for result in results:
        url = result.get("url", "").strip()

        if not url or url in seen_urls:
            continue

        seen_urls.add(url)
        unique_results.append(result)

    return unique_results







def get_research_results(query, original_query=None):
    """
    Fetch industry articles, academic papers, and GitHub projects concurrently.
    """

    query = query.strip() or (
        "embedded systems firmware robotics electronics semiconductors edge AI"
    )

    # Use the original search-box query for GitHub.
    github_query = (
        original_query.strip()
        if original_query is not None
        else query.strip()
    )

    # Run all three independent API searches concurrently.
    with ThreadPoolExecutor(max_workers=3) as executor:
        tavily_future = executor.submit(search_tavily, query)
        arxiv_future = executor.submit(search_arxiv, query)
        github_future = executor.submit(search_github, github_query)

        articles, article_error = tavily_future.result()
        papers, paper_error = arxiv_future.result()
        projects, github_error = github_future.result()

    print("GITHUB PROJECTS RETURNED:", len(projects))
    print("GITHUB ERROR:", github_error)

    # Remove duplicates within each section.
    articles = remove_duplicates(articles)
    papers = remove_duplicates(papers)
    projects = remove_duplicates(projects)

    errors = [
        error
        for error in [article_error, paper_error, github_error]
        if error
    ]

    return {
        "articles": articles,
        "papers": papers,
        "projects": projects,
        "errors": errors,
    }
