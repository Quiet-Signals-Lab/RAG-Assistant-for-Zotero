#zotero_item.py
import fitz
from backend.external_api_utils import fetch_google_book_reviews, fetch_semantic_scholar_data
import logging

logger = logging.getLogger(__name__)

class ZoteroItem:
    def __init__(self, filepath, metadata=None):
        self.filepath = filepath
        self.metadata = metadata or {}  # Allow passing rich dict info

    def get(self, key, default=None):
        """Dict-like access for compatibility: item.get(key)."""
        return self.metadata.get(key, default)

    def __getitem__(self, key):
        return self.metadata.get(key)

    def __setitem__(self, key, value):
        self.metadata[key] = value

    def get_title(self):
        # Try to get title from metadata dict first
        title = self.metadata.get("title")
        if title and title.strip():
            return title.strip()
        # Fallback: Try extracting from PDF metadata
        try:
            doc = fitz.open(self.filepath)
            title = doc.metadata.get("title")
            doc.close()
            if title and title.strip():
                return title.strip()
        except Exception as e:
            logger.info(f"Metadata extraction error (title): {e}")
        return "Untitled"

    def get_author(self):
        # Try to get from meta handle both "author" and "authors"
        author = self.metadata.get("author")
        if author and author.strip():
            return author.strip()
        authors = self.metadata.get("authors")
        if authors and authors.strip():
            return authors.strip()
        # Fallback: Try extracting from PDF metadata
        try:
            doc = fitz.open(self.filepath)
            author = doc.metadata.get("author")
            doc.close()
            if author and author.strip():
                return author.strip()
        except Exception as e:
            logger.info(f"Metadata extraction error (author): {e}")
        return "Unknown author"

    def get_reviews(self):
        # Placeholder: Implement review lookup later (requires more context)
        if self.metadata.get("type") == "book":
            return "Book reviews feature coming soon."
        return "Reviews not available for this item type."


    def __repr__(self):
        return f"<ZoteroItem: {self.get_title()} by {self.get_author()}>"
    
    def items(self):
        return self.metadata.items()
    
    def copy(self):
        return ZoteroItem(filepath=self.filepath, metadata=self.metadata.copy())
    
    @staticmethod
    def get_gbook_reviews(isbn, google_api_key):
        return fetch_google_book_reviews(isbn, google_api_key)
