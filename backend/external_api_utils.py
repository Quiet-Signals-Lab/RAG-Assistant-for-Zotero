#external_api_utils.py
"""
External API utilities for fetching metadata and reviews from external services.

Provides functions for:
- Google Books API: Fetch book reviews and metadata
- Semantic Scholar API: Fetch paper citations, references, and abstracts
"""

import requests
from semanticscholar import SemanticScholar
import os
import logging
from typing import Optional, Dict, List, Any, Union
from dotenv import load_dotenv

# Initialize logger
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
google_api_key = os.getenv("GOOGLE_API")


def fetch_google_book_reviews(isbn: str, google_api_key: str) -> List[Dict[str, Any]]:
    """
    Fetch book reviews and metadata from Google Books API.
    
    Args:
        isbn: Book ISBN (10 or 13 digits)
        google_api_key: Google Books API key
        
    Returns:
        List of book review dictionaries with title, authors, description, etc.
        Returns empty list if not found or on error.
        
    Raises:
        ValueError: If ISBN or API key is missing/invalid
    """
    if not isbn or not isbn.strip():
        raise ValueError("ISBN is required")
    
    if not google_api_key or not google_api_key.strip():
        raise ValueError("Google API key is required")
    
    try:
        resp = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f"isbn:{isbn}", "key": google_api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        
        reviews = []
        for item in data.get('items', []):
            volume_info = item.get('volumeInfo', {})
            reviews.append({
                'title': volume_info.get('title'),
                'authors': volume_info.get('authors', []),
                'description': volume_info.get('description', ''),
                'preview_link': volume_info.get('previewLink', ''),
                'info_link': volume_info.get('infoLink', '')
            })
        return reviews
        
    except requests.exceptions.Timeout:
        logger.error(f"Google Books API timeout for ISBN {isbn}")
        return []
    except requests.exceptions.HTTPError as e:
        logger.error(f"Google Books API HTTP error: {e}")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Google Books API error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in fetch_google_book_reviews: {e}")
        return []


def fetch_semantic_scholar_data(
    doi: Optional[str] = None,
    title: Optional[str] = None,
    authors: Optional[Union[str, List[str]]] = None
) -> Optional[Dict[str, Any]]:
    """
    Fetch paper metadata from Semantic Scholar API.
    
    Tries DOI lookup first, falls back to title/author search if DOI fails.
    
    Args:
        doi: Paper DOI (preferred lookup method)
        title: Paper title (fallback if DOI fails)
        authors: Author names as string (comma-separated) or list (helps with fallback matching)
        
    Returns:
        Dictionary with paper metadata including:
        - title, abstract, year, authors
        - citation_count, citations, references
        - url, doi
        Returns None if paper not found.
    """
    if not doi and not title:
        logger.warning("Either DOI or title must be provided for Semantic Scholar lookup")
        return None
    
    sch = SemanticScholar()
    paper = None
    
    # Try DOI lookup first
    if doi:
        try:
            logger.info(f"Attempting Semantic Scholar lookup with DOI: {doi}")
            paper = sch.get_paper(f"DOI:{doi}")
        except Exception as e:
            logger.warning(f"Semantic Scholar DOI lookup failed for {doi}: {e}")
    
    # Fallback to title search if DOI failed or not provided
    if not paper and title:
        try:
            logger.info(f"Attempting Semantic Scholar title search: {title}")
            results = sch.search_paper(title, limit=5)
            
            if results and len(results) > 0:
                # If authors provided, try to match by author
                if authors:
                    paper = _match_paper_by_author(results, authors)
                else:
                    # Take best match (first result)
                    paper = results[0]
                    
                if paper:
                    logger.info(f"Found paper via title search: {paper.get('title', 'Unknown')}")
        except Exception as e:
            logger.warning(f"Semantic Scholar title search failed for '{title}': {e}")
    
    # Extract and return data if paper was found
    if paper:
        try:
            return {
                'title': paper.get('title', ''),
                'abstract': paper.get('abstract', ''),
                'year': paper.get('year'),
                'authors': [a.get('name') for a in paper.get('authors', []) if a.get('name')],
                'citation_count': paper.get('citationCount', 0),
                'citations': paper.get('citations', [])[:50],  # Limit to first 50
                'references': paper.get('references', [])[:50],  # Limit to first 50
                'url': paper.get('url', ''),
                'doi': paper.get('externalIds', {}).get('DOI') if paper.get('externalIds') else None,
            }
        except Exception as e:
            logger.error(f"Error extracting Semantic Scholar paper data: {e}")
            return None
    
    logger.info(f"Paper not found in Semantic Scholar (DOI: {doi}, Title: {title})")
    return None


def _match_paper_by_author(results: List[Any], authors_str: Union[str, List[str]]) -> Optional[Any]:
    """
    Helper to match paper from search results by author names.
    
    Args:
        results: List of paper results from Semantic Scholar
        authors_str: String of author names (comma-separated or space-separated) or list of names
        
    Returns:
        Best matching paper or first result if no good match found
    """
    if not results:
        return None
    
    # Handle both string and list inputs for authors
    if isinstance(authors_str, list):
        # Join list into comma-separated string
        authors_str = ', '.join(str(a) for a in authors_str if a)
    
    if not authors_str:
        return results[0]
    
    # Normalize author string for comparison
    search_authors = authors_str.lower().replace(',', ' ').split()
    
    # Try to find paper with matching author
    # Score each paper by number of matching author name parts
    best_match = None
    best_score = 0
    
    for paper in results:
        paper_authors = paper.get('authors', [])
        score = 0
        
        for author in paper_authors:
            author_name = author.get('name', '').lower()
            # Count how many search terms appear in this author name
            for search_author in search_authors:
                if len(search_author) > 2 and search_author in author_name:
                    score += 1
        
        if score > best_score:
            best_score = score
            best_match = paper
    
    # Return best match if we found any matches, otherwise first result
    if best_match:
        logger.info(f"Matched paper by author with score {best_score}")
        return best_match
    
    logger.info("No author match found, using first search result")
    return results[0]

