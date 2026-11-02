from django.core.paginator import Paginator
from django.shortcuts import render

from .services import get_research_results, search_arxiv


DEFAULT_QUERY = (
    "embedded systems firmware robotics electronics semiconductors edge AI"
)
RESULTS_PER_PAGE = 6


def home(request):
    # Original value entered in the search box.
    query = request.GET.get("q", "").strip()

    # Default query used for industry news and research papers.
    search_query = query or DEFAULT_QUERY

    articles = []
    papers = []
    projects = []
    errors = []

    try:
        # Pass the original query separately so GitHub can use
        # its own default when the search box is empty.
        results = get_research_results(
            search_query,
            original_query=query,
        ) or {}

        articles = results.get("articles", []) or []
        papers = results.get("papers", []) or []
        projects = results.get("projects", []) or []

        result_errors = results.get("errors", []) or []

        if isinstance(result_errors, str):
            errors.append(result_errors)
        else:
            errors.extend(result_errors)

        # On the homepage, try a default arXiv search if no papers were found.
        if not query and not papers:
            extra_papers, arxiv_error = search_arxiv("")

            if extra_papers:
                papers = extra_papers

            if arxiv_error:
                errors.append(arxiv_error)

    except Exception as error:
        print(f"Research search failed: {error}")
        errors.append("Unable to fetch results. Please try again.")

    # Each section has its own paginator: six results per page.
    industry_news = Paginator(
        articles, RESULTS_PER_PAGE
    ).get_page(request.GET.get("news_page", 1))

    research_papers = Paginator(
        papers, RESULTS_PER_PAGE
    ).get_page(request.GET.get("papers_page", 1))

    github_projects = Paginator(
        projects, RESULTS_PER_PAGE
    ).get_page(request.GET.get("projects_page", 1))

    context = {
        "query": query,
        "search_query": query,
        "industry_news": industry_news,
        "research_papers": research_papers,
        "github_projects": github_projects,
        "total_results": len(articles) + len(papers) + len(projects),
        "errors": errors,
    }

    return render(request, "research_app/home.html", context)
