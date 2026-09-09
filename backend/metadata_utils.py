"""
Utilities for building ChromaDB metadata filter clauses.
Constructs where clauses for metadata-based filtering.
"""

from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


def build_metadata_where_clause(
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    tags: Optional[List[str]] = None,
    collections: Optional[List[str]] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
    item_types: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Build a where clause for metadata filtering.
    
    IMPORTANT: Tags, collections, title, and author use $contains which is NOT supported by ChromaDB.
    This function returns a clause that must be split using separate_where_clauses().
    
    ChromaDB only supports: $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, $and, $or
    The $contains operator must be applied client-side after retrieval.
    
    NOTE: Year values of -1 indicate "no year" (ChromaDB strips None values).
    Year filters automatically exclude -1 values, so items without years won't match year-based queries.
    
    Args:
        year_min: Minimum year (inclusive)
        year_max: Maximum year (inclusive)
        tags: List of tags to match (any tag matches)
        collections: List of collections to match (any collection matches)
        title: Title substring to match (case-insensitive)
        author: Author substring to match (case-insensitive)
        item_types: List of item types to match (any type matches, uses $in - ChromaDB compatible)
    
    Returns:
        Where clause dict with potentially unsupported $contains operators, or None if no filters
    
    Examples:
        # Year range only (ChromaDB-compatible)
        {"$and": [{"year": {"$gte": 2015}}, {"year": {"$lte": 2020}}]}
        
        # Tags only (requires client-side filtering)
        {"$or": [{"tags": {"$contains": "NLP"}}, {"tags": {"$contains": "ML"}}]}
        
        # Complex: year + tags + title (mixed)
        {"$and": [
            {"year": {"$gte": 2018}},
            {"$or": [{"tags": {"$contains": "NLP"}}, {"tags": {"$contains": "Transformers"}}]},
            {"title": {"$contains": "neural"}}
        ]}
    """
    conditions = []
    
    # Year range conditions (automatically excludes year=-1)
    if year_min is not None:
        conditions.append({"year": {"$gte": year_min}})
    
    if year_max is not None:
        conditions.append({"year": {"$lte": year_max}})
    
    # Tags conditions (any tag matches) - uses $contains_item which requires client-side filtering
    if tags:
        tag_conditions = [{"tags": {"$contains_item": tag}} for tag in tags]
        if len(tag_conditions) == 1:
            conditions.append(tag_conditions[0])
        else:
            conditions.append({"$or": tag_conditions})
    
    # Collections conditions (any collection matches) - uses $contains_item which requires client-side filtering
    if collections:
        coll_conditions = [{"collections": {"$contains_item": coll}} for coll in collections]
        if len(coll_conditions) == 1:
            conditions.append(coll_conditions[0])
        else:
            conditions.append({"$or": coll_conditions})
    
    # Title condition (substring match) - uses $contains which requires client-side filtering
    if title:
        conditions.append({"title": {"$contains": title}})
    
    # Author condition (substring match) - uses $contains which requires client-side filtering
    if author:
        conditions.append({"authors": {"$contains": author}})
    
    # Item type conditions (any type matches) - uses $in which is ChromaDB-compatible
    if item_types:
        # Map UI display names to Zotero internal names (for backward compatibility)
        item_type_mapping = {
            "Journal Article": "journalArticle",
            "Book": "book",
            "Book Section": "bookSection",
            "Conference Paper": "conferencePaper",
            "Thesis": "thesis",
            "Preprint": "preprint",
            "Web Page": "webpage",
            "Report": "report",
            "Presentation": "presentation",
            "Manuscript": "manuscript",
        }
        # Convert display names to internal names
        internal_types = []
        for display_type in item_types:
            # If it's a display name, map it. Otherwise assume it's already an internal name.
            internal_type = item_type_mapping.get(display_type, display_type)
            internal_types.append(internal_type)
        
        if len(internal_types) == 1:
            conditions.append({"item_type": {"$eq": internal_types[0]}})
        else:
            conditions.append({"item_type": {"$in": internal_types}})
    
    # Combine all conditions
    if not conditions:
        return None
    
    if len(conditions) == 1:
        return conditions[0]
    
    return {"$and": conditions}


def separate_where_clauses(
    where: Optional[Dict[str, Any]]
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Separate a where clause into ChromaDB-compatible and client-side filters.
    
    ChromaDB only supports: $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, $and, $or
    The $contains / $contains_item operators must be filtered client-side after retrieval.
    
    Args:
        where: Where clause that may contain unsupported operators
    
    Returns:
        Tuple of (chroma_where, client_where). Either can be None.
        - chroma_where: Filters that can be passed to ChromaDB
        - client_where: Filters that must be applied client-side (contains $contains)
    
    Examples:
        # Input: {"year": {"$gte": 2015}}
        # Output: ({"year": {"$gte": 2015}}, None)
        
        # Input: {"tags": {"$contains": "NLP"}}
        # Output: (None, {"tags": {"$contains": "NLP"}})
        
        # Input: {"$and": [{"year": {"$gte": 2015}}, {"tags": {"$contains": "NLP"}}]}
        # Output: ({"year": {"$gte": 2015}}, {"tags": {"$contains": "NLP"}})
    """
    if where is None:
        return None, None
    
    chroma_supported_ops = {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"}
    logical_ops = {"$and", "$or", "$not"}
    
    def _has_contains(clause: Dict[str, Any]) -> bool:
        """Check if clause contains $contains operator"""
        for key, value in clause.items():
            if key.startswith("$contains"):  # $contains, $contains_item
                return True
            if isinstance(value, dict):
                if _has_contains(value):
                    return True
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and _has_contains(item):
                        return True
        return False
    
    def _extract_conditions(clause: Dict[str, Any]) -> tuple[list, list]:
        """Extract conditions and separate them into chroma-compatible and client-side"""
        chroma_conditions = []
        client_conditions = []
        
        # Handle logical operators at root
        if "$and" in clause:
            for condition in clause["$and"]:
                if _has_contains(condition):
                    client_conditions.append(condition)
                else:
                    chroma_conditions.append(condition)
            return chroma_conditions, client_conditions
        
        if "$or" in clause:
            # Can't split OR conditions - if any use $contains, all must be client-side
            if _has_contains(clause):
                return [], [clause]
            return [clause], []
        
        # Single condition
        if _has_contains(clause):
            return [], [clause]
        return [clause], []
    
    chroma_conds, client_conds = _extract_conditions(where)
    
    # Build result clauses
    chroma_where = None
    if chroma_conds:
        if len(chroma_conds) == 1:
            chroma_where = chroma_conds[0]
        else:
            chroma_where = {"$and": chroma_conds}
    
    client_where = None
    if client_conds:
        if len(client_conds) == 1:
            client_where = client_conds[0]
        else:
            client_where = {"$and": client_conds}
    
    return chroma_where, client_where


def apply_client_side_filters(
    results: Dict[str, Any],
    client_where: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Apply client-side filters (with $contains) to ChromaDB results.
    
    Args:
        results: ChromaDB query results dict with 'documents', 'metadatas', 'ids', 'distances'
        client_where: Client-side where clause with $contains operators
    
    Returns:
        Filtered results dict in same format as ChromaDB results
    """
    if client_where is None:
        return results
    
    docs_outer = results.get("documents", [[]])
    metas_outer = results.get("metadatas", [[]])
    ids_outer = results.get("ids", [[]])
    dists_outer = results.get("distances", [[]])
    
    # Handle nested list structure from ChromaDB
    if not docs_outer or not docs_outer[0]:
        return results
    
    docs = docs_outer[0]
    metas = metas_outer[0] if metas_outer else []
    ids = ids_outer[0] if ids_outer else []
    dists = dists_outer[0] if dists_outer else []
    
    # Filter based on client_where clause
    filtered = []
    for i, meta in enumerate(metas):
        if _matches_where_clause(meta, client_where):
            filtered.append(i)
    
    # Build filtered results
    return {
        "documents": [[docs[i] for i in filtered]] if docs else [[]],
        "metadatas": [[metas[i] for i in filtered]] if metas else [[]],
        "ids": [[ids[i] for i in filtered]] if ids else [[]],
        "distances": [[dists[i] for i in filtered]] if dists else [[]],
    }


def _matches_where_clause(metadata: Dict[str, Any], where: Dict[str, Any]) -> bool:
    """
    Check if metadata matches a where clause (supports $contains for client-side filtering).
    
    Args:
        metadata: Metadata dict
        where: Where clause dict
    
    Returns:
        True if metadata matches the where clause
    """
    for key, condition in where.items():
        # Handle logical operators
        if key == "$and":
            if not all(_matches_where_clause(metadata, c) for c in condition):
                return False
        elif key == "$or":
            if not any(_matches_where_clause(metadata, c) for c in condition):
                return False
        elif key == "$not":
            if _matches_where_clause(metadata, condition):
                return False
        else:
            # Field-level condition
            field_value = metadata.get(key)
            
            if isinstance(condition, dict):
                # Field has operators
                for op, target in condition.items():
                    if op == "$eq":
                        if field_value != target:
                            return False
                    elif op == "$ne":
                        if field_value == target:
                            return False
                    elif op == "$gt":
                        if not (field_value > target):
                            return False
                    elif op == "$gte":
                        if not (field_value >= target):
                            return False
                    elif op == "$lt":
                        if not (field_value < target):
                            return False
                    elif op == "$lte":
                        if not (field_value <= target):
                            return False
                    elif op == "$contains":
                        # Case-insensitive substring matching for better UX
                        if target.lower() not in str(field_value).lower():
                            return False
                    elif op == "$contains_item":
                        # Whole-entry match against a comma-joined list (tags,
                        # collections). Substring matching would let the
                        # collection "Faith" also select items whose only
                        # collection is "Faith Studies". See issue #75.
                        entries = {e.strip().lower() for e in str(field_value).split(",")}
                        if target.strip().lower() not in entries:
                            return False
                    elif op == "$in":
                        if field_value not in target:
                            return False
                    elif op == "$nin":
                        if field_value in target:
                            return False
            else:
                # Direct equality check
                if field_value != condition:
                    return False
    
    return True


def validate_where_clause(where: Optional[Dict[str, Any]]) -> bool:
    """
    Validate a ChromaDB where clause structure.
    
    Args:
        where: Where clause dict
    
    Returns:
        True if valid, False otherwise
    """
    if where is None:
        return True
    
    if not isinstance(where, dict):
        return False
    
    # Allowed operators
    logical_ops = {"$and", "$or", "$not"}
    comparison_ops = {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin", "$contains", "$contains_item"}
    
    # Recursive validation
    for key, value in where.items():
        if key in logical_ops:
            # Logical operators should have list values
            if not isinstance(value, list):
                return False
            # Recursively validate each condition
            for condition in value:
                if not validate_where_clause(condition):
                    return False
        elif key in comparison_ops:
            # Comparison operators can have various value types
            continue
        else:
            # Must be a field name with nested operators
            if not isinstance(value, dict):
                continue
            if not validate_where_clause(value):
                return False
    
    return True


def merge_where_clauses(
    clause1: Optional[Dict[str, Any]],
    clause2: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Merge two where clauses with AND logic.
    
    Args:
        clause1: First where clause
        clause2: Second where clause
    
    Returns:
        Combined where clause, or None if both are None
    """
    if clause1 is None and clause2 is None:
        return None
    
    if clause1 is None:
        return clause2
    
    if clause2 is None:
        return clause1
    
    # Both clauses exist, combine with AND
    return {"$and": [clause1, clause2]}


def format_filters_for_display(
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    tags: Optional[List[str]] = None,
    collections: Optional[List[str]] = None,
) -> str:
    """
    Format filters into a human-readable string for display.
    
    Args:
        year_min: Minimum year
        year_max: Maximum year
        tags: List of tags
        collections: List of collections
    
    Returns:
        Formatted string (e.g., "Year: 2015-2020, Tags: NLP, ML")
    """
    parts = []
    
    # Year range
    if year_min and year_max:
        if year_min == year_max:
            parts.append(f"Year: {year_min}")
        else:
            parts.append(f"Year: {year_min}-{year_max}")
    elif year_min:
        parts.append(f"Year: {year_min}+")
    elif year_max:
        parts.append(f"Year: ≤{year_max}")
    
    # Tags
    if tags:
        parts.append(f"Tags: {', '.join(tags)}")
    
    # Collections
    if collections:
        parts.append(f"Collections: {', '.join(collections)}")
    
    return " | ".join(parts) if parts else "No filters"


# Example usage and tests
if __name__ == "__main__":
    # Example 1: Year range only
    where1 = build_metadata_where_clause(year_min=2015, year_max=2020)
    print("Example 1 (Year range):")
    print(where1)
    print(f"Valid: {validate_where_clause(where1)}")
    print()
    
    # Example 2: Tags only
    where2 = build_metadata_where_clause(tags=["NLP", "Transformers", "Deep Learning"])
    print("Example 2 (Tags):")
    print(where2)
    print(f"Valid: {validate_where_clause(where2)}")
    print()
    
    # Example 3: Complex (year + tags + collections)
    where3 = build_metadata_where_clause(
        year_min=2018,
        tags=["NLP"],
        collections=["PhD Research", "Survey Papers"]
    )
    print("Example 3 (Complex):")
    print(where3)
    print(f"Valid: {validate_where_clause(where3)}")
    print()
    
    # Example 4: Merge clauses
    merged = merge_where_clauses(where1, where2)
    print("Example 4 (Merged):")
    print(merged)
    print(f"Valid: {validate_where_clause(merged)}")
    print()
    
    # Example 5: Display formatting
    display = format_filters_for_display(
        year_min=2015,
        year_max=2020,
        tags=["NLP", "ML"],
        collections=["Research"]
    )
    print("Example 5 (Display):")
    print(display)
