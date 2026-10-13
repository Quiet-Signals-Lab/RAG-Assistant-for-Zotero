#zotero_dbase.py
import sqlite3
import os
import threading
from contextlib import contextmanager
from backend.zoteroitem import ZoteroItem
from pathlib import Path

class ZoteroLibrary:
    def __init__(self, db_path, storage_path=None):
        self.db_path = db_path
        self.storage_path = storage_path
        self._local = threading.local()
        self._lock = threading.Lock()
    
    def _get_connection(self):
        """Get or create thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                f'file:{self.db_path}?mode=ro', 
                uri=True, 
                check_same_thread=True  # Changed to True for safety
            )
            # Enable shared cache for read-only connections
            self._local.conn.isolation_level = None
        return self._local.conn
    
    @contextmanager
    def _cursor(self):
        """Context manager for thread-safe cursor access."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def search_parent_items(self, 
                            authors=None, 
                            titles=None, 
                            dates=None, 
                            tags=None, 
                            collections=None):
        filters = []
        params = []

        # Author filter
        if authors:
            filters.append("(" + " OR ".join(["cr.lastName LIKE ?"] * len(authors)) + ")")
            params += [f"%{author}%" for author in authors]
        # Title filter
        if titles:
            filters.append("(" + " OR ".join(["v_title.value LIKE ?"] * len(titles)) + ")")
            params += [f"%{title}%" for title in titles]
        # Date filter
        if dates:
            filters.append("(" + " OR ".join(["v_date.value LIKE ?"] * len(dates)) + ")")
            params += [f"%{date}%" for date in dates]
        # Tag filter
        if tags:
            filters.append("(" + " OR ".join(["t.name LIKE ?"] * len(tags)) + ")")
            params += [f"%{tag}%" for tag in tags]
        # Collection filter
        if collections:
            filters.append("(" + " OR ".join(["c.collectionName LIKE ?"] * len(collections)) + ")")
            params += [f"%{coll}%" for coll in collections]

        where_clause = " AND ".join(filters) if filters else "1"
        query = f"""
        SELECT 
            i.itemID,
            i.key,
            v_title.value AS title,
            v_date.value AS date
        FROM items i
        JOIN itemCreators ic ON i.itemID = ic.itemID
        JOIN creators cr ON ic.creatorID = cr.creatorID
        JOIN itemData d_title ON i.itemID = d_title.itemID AND d_title.fieldID = (SELECT fieldID FROM fields WHERE fieldName = 'title')
        JOIN itemDataValues v_title ON d_title.valueID = v_title.valueID
        LEFT JOIN itemData d_date ON i.itemID = d_date.itemID AND d_date.fieldID = (SELECT fieldID FROM fields WHERE fieldName = 'date')
        LEFT JOIN itemDataValues v_date ON d_date.valueID = v_date.valueID
        LEFT JOIN itemTags it ON i.itemID = it.itemID
        LEFT JOIN tags t ON it.tagID = t.tagID
        LEFT JOIN collectionItems ci ON i.itemID = ci.itemID
        LEFT JOIN collections c ON ci.collectionID = c.collectionID
        WHERE {where_clause}
        """
        with self._cursor() as cur:
            cur.execute(query, tuple(params))
            return cur.fetchall()
    

    def search_parent_items_with_pdfs(self):
        """Return every parent item that has a PDF attachment.

        Took author/title/date/tag/collection arguments that were never
        implemented — the filter block was a stub, so any caller passing them
        silently got the whole library back. No caller passed them; filtering
        happens downstream on the indexed metadata instead. See issue #75.

        Creators are a left join: an inner join left out every item without a
        creator (12 in one real library), which could then never be indexed.
        """
        query = """
        SELECT 
            i.itemID,
            i.key,
            v_title.value AS title,
            v_date.value AS date,
            GROUP_CONCAT(DISTINCT cr.lastName) AS authors,
            GROUP_CONCAT(DISTINCT t.name) AS tags,
            GROUP_CONCAT(DISTINCT c.collectionName) AS collections,
            att.key AS attachment_key,
            att_path.path AS attachment_path,
            itemType.typeName AS item_type
        FROM items i
        JOIN itemTypes itemType ON i.itemTypeID = itemType.itemTypeID
        LEFT JOIN itemCreators ic ON i.itemID = ic.itemID
        LEFT JOIN creators cr ON ic.creatorID = cr.creatorID
        JOIN itemData d_title ON i.itemID = d_title.itemID AND d_title.fieldID = (SELECT fieldID FROM fields WHERE fieldName = 'title')
        JOIN itemDataValues v_title ON d_title.valueID = v_title.valueID
        LEFT JOIN itemData d_date ON i.itemID = d_date.itemID AND d_date.fieldID = (SELECT fieldID FROM fields WHERE fieldName = 'date')
        LEFT JOIN itemDataValues v_date ON d_date.valueID = v_date.valueID
        LEFT JOIN itemTags it ON i.itemID = it.itemID
        LEFT JOIN tags t ON it.tagID = t.tagID
        LEFT JOIN collectionItems ci ON i.itemID = ci.itemID
        LEFT JOIN collections c ON ci.collectionID = c.collectionID

        LEFT JOIN itemAttachments ia ON i.itemID = ia.parentItemID
        LEFT JOIN items att ON ia.itemID = att.itemID
        LEFT JOIN itemData att_data ON att.itemID = att_data.itemID AND att_data.fieldID = (SELECT fieldID FROM fields WHERE fieldName = 'mimeType')
        LEFT JOIN itemDataValues att_mime ON att_data.valueID = att_mime.valueID
        LEFT JOIN itemAttachments att_path ON att.itemID = att_path.itemID

        WHERE (att_mime.value = 'application/pdf' OR att_path.path LIKE '%.pdf')
        GROUP BY i.itemID
        """

        with self._cursor() as cur:
            cur.execute(query)
            results = cur.fetchall()
        # Use cross-platform path relative to Zotero database location
        # The storage directory is typically at the same level as the database
        db_parent = Path(self.db_path).parent
        storage_dir = self.storage_path if self.storage_path else str(db_parent / "storage")
        zotero_items = []

        for item in results:
            pdf_full_path = None
            if item[7] and item[8]:
                raw_path = item[8]

                if raw_path.startswith('storage:'):
                    # Stored file: path is relative filename inside storage_dir/attach_key/
                    base_filename = os.path.basename(raw_path[len('storage:'):])
                    pdf_full_path = os.path.join(storage_dir, item[7], base_filename) if base_filename else None
                elif os.path.isabs(raw_path):
                    # Linked file with absolute path (e.g. ZotMoov): use as-is
                    pdf_full_path = raw_path
                elif raw_path.startswith('attachments:'):
                    # Linked file with path relative to Zotero's linked-file base directory.
                    # When a custom storage_path is configured we treat it as that base dir.
                    relative_path = raw_path[len('attachments:'):]
                    pdf_full_path = os.path.join(storage_dir, relative_path)
                else:
                    # Unknown format: best-effort using basename under storage_dir/attach_key
                    base_filename = os.path.basename(raw_path)
                    pdf_full_path = os.path.join(storage_dir, item[7], base_filename) if base_filename else None

            metadata = {
                'item_id': str(item[0]),
                'key': item[1],
                'title': item[2],
                'date': item[3],
                'authors': item[4],       
                'tags': item[5],           
                'collections': item[6],    
                'attachment_key': item[7],
                'attachment_path': item[8],
                'item_type': item[9] or "",
                'pdf_path': pdf_full_path
            }
            zotero_items.append(ZoteroItem(filepath=pdf_full_path, metadata=metadata))
        return zotero_items
    
    def get_all_tags(self):
        """Get all unique tags from the library."""
        with self._cursor() as cur:
            # Query for tags from items that have PDFs
            cur.execute("""
                SELECT DISTINCT t.name
                FROM tags t
                INNER JOIN itemTags it ON t.tagID = it.tagID
                INNER JOIN items i ON it.itemID = i.itemID
                WHERE i.itemID IN (
                    SELECT DISTINCT parentItemID
                    FROM itemAttachments
                    WHERE contentType = 'application/pdf'
                    AND parentItemID IS NOT NULL
                )
                ORDER BY t.name
            """)
            return [row[0] for row in cur.fetchall() if row[0]]
    
    def get_common_tags(self, share=0.01, min_items=10):
        """Tags on at least `share` of the items with PDFs (and `min_items` of them): a
        classification or housekeeping tag ("notion", "to read"), not a subject."""
        with self._cursor() as cur:
            cur.execute("""
                SELECT t.name, COUNT(DISTINCT it.itemID)
                FROM tags t JOIN itemTags it ON it.tagID = t.tagID
                WHERE it.itemID IN (SELECT parentItemID FROM itemAttachments WHERE contentType = 'application/pdf')
                GROUP BY t.name
            """)
            counts = cur.fetchall()
            cur.execute("SELECT COUNT(DISTINCT parentItemID) FROM itemAttachments WHERE contentType = 'application/pdf'")
            total = cur.fetchone()[0]
        floor = max(min_items, share * total)
        return {name for name, n in counts if name and n >= floor}

    def get_all_collections(self):
        """Get all collections with item counts."""
        with self._cursor() as cur:
            # Query for collections and count items with PDFs
            cur.execute("""
                SELECT c.collectionName, COUNT(DISTINCT ci.itemID) as item_count
                FROM collections c
                LEFT JOIN collectionItems ci ON c.collectionID = ci.collectionID
                WHERE ci.itemID IN (
                    SELECT DISTINCT parentItemID
                    FROM itemAttachments
                    WHERE contentType = 'application/pdf'
                    AND parentItemID IS NOT NULL
                )
                GROUP BY c.collectionID
                HAVING item_count > 0
                ORDER BY c.collectionName
            """)
            return [
                {"name": row[0], "count": row[1]}
                for row in cur.fetchall()
                if row[0]
            ]
    
    def get_all_item_types(self):
        """Get all item types with counts from items with PDFs."""
        with self._cursor() as cur:
            # Query for item types and count items with PDFs
            cur.execute("""
                SELECT it.typeName, COUNT(DISTINCT i.itemID) as item_count
                FROM itemTypes it
                INNER JOIN items i ON it.itemTypeID = i.itemTypeID
                WHERE i.itemID IN (
                    SELECT DISTINCT parentItemID
                    FROM itemAttachments
                    WHERE contentType = 'application/pdf'
                    AND parentItemID IS NOT NULL
                )
                GROUP BY it.itemTypeID, it.typeName
                HAVING item_count > 0
                ORDER BY item_count DESC, it.typeName
            """)
            return [
                {"name": row[0], "count": row[1]}
                for row in cur.fetchall()
                if row[0]
            ]
    
    # Fields read for a citation. Zotero stores the type-specific field name
    # (bookTitle, proceedingsTitle, university ...), so all of them are asked for.
    _BIB_FIELDS = (
        "title", "shortTitle", "date", "publicationTitle", "bookTitle", "proceedingsTitle",
        "websiteTitle", "blogTitle", "volume", "issue", "pages", "publisher", "institution",
        "university", "place", "DOI", "ISBN", "url", "edition", "reportNumber", "thesisType",
    )
    _PARENT_TYPES_SQL = "t.typeName NOT IN ('attachment', 'note', 'annotation')"

    def get_bibliographic(self, item_ids):
        """Citation data for items, keyed by item id as a string.

        One read-only query per table, so a page of results costs three queries.
        Ids that are not in the library are left out.
        """
        ids = sorted({int(i) for i in item_ids if str(i).strip().isdigit()})
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        raw = {}
        with self._cursor() as cur:
            cur.execute(f"""
                SELECT i.itemID, i.key, t.typeName, g.groupID
                FROM items i
                JOIN itemTypes t ON t.itemTypeID = i.itemTypeID
                LEFT JOIN groups g ON g.libraryID = i.libraryID
                WHERE i.itemID IN ({marks})
            """, ids)
            for item_id, key, type_name, group_id in cur.fetchall():
                raw[str(item_id)] = {
                    "item_id": str(item_id), "item_key": key, "item_type": type_name,
                    "group_id": group_id, "pdf_key": None, "creators": [], "fields": {},
                }
            field_marks = ",".join("?" * len(self._BIB_FIELDS))
            cur.execute(f"""
                SELECT d.itemID, f.fieldName, v.value
                FROM itemData d
                JOIN fields f ON f.fieldID = d.fieldID
                JOIN itemDataValues v ON v.valueID = d.valueID
                WHERE d.itemID IN ({marks}) AND f.fieldName IN ({field_marks})
            """, ids + list(self._BIB_FIELDS))
            for item_id, name, value in cur.fetchall():
                if str(item_id) in raw:
                    raw[str(item_id)]["fields"][name] = value
            cur.execute(f"""
                SELECT ic.itemID, c.firstName, c.lastName, ct.creatorType
                FROM itemCreators ic
                JOIN creators c ON c.creatorID = ic.creatorID
                JOIN creatorTypes ct ON ct.creatorTypeID = ic.creatorTypeID
                WHERE ic.itemID IN ({marks})
                ORDER BY ic.itemID, ic.orderIndex
            """, ids)
            for item_id, first, last, role in cur.fetchall():
                if str(item_id) in raw:
                    raw[str(item_id)]["creators"].append({"first": first or "", "last": last or "", "role": role})
            # The PDF attachment's own key: Zotero opens a reader at a page by attachment, not parent.
            cur.execute(f"""
                SELECT ia.parentItemID, a.key
                FROM itemAttachments ia
                JOIN items a ON a.itemID = ia.itemID
                WHERE ia.parentItemID IN ({marks})
                  AND (ia.contentType = 'application/pdf' OR ia.path LIKE '%.pdf')
                  AND ia.itemID NOT IN (SELECT itemID FROM deletedItems)
                ORDER BY ia.parentItemID, a.itemID
            """, ids)
            for parent_id, key in cur.fetchall():
                entry = raw.get(str(parent_id))
                if entry is not None and not entry["pdf_key"]:
                    entry["pdf_key"] = key
        return {item_id: _citation(entry) for item_id, entry in raw.items()}

    def find_items_by_field(self, field_names, needle, normalise=False, limit=25):
        """Parent items with a field (DOI, ISBN, title ...) containing `needle`.

        Case-insensitive for ASCII. `normalise` strips hyphens and spaces from the
        stored value first, for ISBNs. Returns [(item_id, value)].
        """
        if not needle or not field_names:
            return []
        value = "REPLACE(REPLACE(v.value, '-', ''), ' ', '')" if normalise else "v.value"
        marks = ",".join("?" * len(field_names))
        with self._cursor() as cur:
            cur.execute(f"""
                SELECT DISTINCT i.itemID, v.value
                FROM items i
                JOIN itemTypes t ON t.itemTypeID = i.itemTypeID
                JOIN itemData d ON d.itemID = i.itemID
                JOIN fields f ON f.fieldID = d.fieldID
                JOIN itemDataValues v ON v.valueID = d.valueID
                WHERE f.fieldName IN ({marks})
                  AND {self._PARENT_TYPES_SQL}
                  AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
                  AND {value} LIKE ? ESCAPE '\\'
                LIMIT ?
            """, list(field_names) + [f"%{_like_escape(needle)}%", limit])
            return [(str(item_id), val) for item_id, val in cur.fetchall()]

    def find_items_by_creator_year(self, last_name, year, limit=25):
        """Parent items with a creator whose last name starts with `last_name`, dated `year`."""
        if not last_name or not year:
            return []
        with self._cursor() as cur:
            cur.execute(f"""
                SELECT DISTINCT i.itemID
                FROM items i
                JOIN itemTypes t ON t.itemTypeID = i.itemTypeID
                JOIN itemCreators ic ON ic.itemID = i.itemID
                JOIN creators c ON c.creatorID = ic.creatorID
                JOIN itemData d ON d.itemID = i.itemID
                JOIN fields f ON f.fieldID = d.fieldID AND f.fieldName = 'date'
                JOIN itemDataValues v ON v.valueID = d.valueID
                WHERE c.lastName LIKE ? ESCAPE '\\'
                  AND v.value LIKE ?
                  AND {self._PARENT_TYPES_SQL}
                  AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
                LIMIT ?
            """, (f"{_like_escape(last_name)}%", f"{int(year)}%", limit))
            return [str(row[0]) for row in cur.fetchall()]

    def get_doi_and_title_index(self):
        """Every parent item's DOI and title, for marking the references a reader already owns.

        Returns ({doi: item_id}, {title: item_id}) with DOIs lowercased and titles as
        they are stored; callers normalise titles their own way.
        """
        dois, titles = {}, {}
        with self._cursor() as cur:
            cur.execute(f"""
                SELECT i.itemID, f.fieldName, v.value
                FROM items i
                JOIN itemTypes t ON t.itemTypeID = i.itemTypeID
                JOIN itemData d ON d.itemID = i.itemID
                JOIN fields f ON f.fieldID = d.fieldID
                JOIN itemDataValues v ON v.valueID = d.valueID
                WHERE f.fieldName IN ('DOI', 'title')
                  AND {self._PARENT_TYPES_SQL}
                  AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
            """)
            for item_id, field, value in cur.fetchall():
                if field == "DOI" and value:
                    dois.setdefault(str(value).strip().lower(), str(item_id))
                elif value:
                    titles.setdefault(str(value), str(item_id))
        return dois, titles

    def get_creator_last_names(self):
        """Every creator surname in the library, for reading "by X" in a search request."""
        with self._cursor() as cur:
            cur.execute("SELECT DISTINCT lastName FROM creators WHERE lastName IS NOT NULL AND lastName != ''")
            return [row[0] for row in cur.fetchall()]

    def close(self):
        """Close thread-local connections. Call this on shutdown."""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None



def _like_escape(text):
    return str(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _first(fields, *names):
    return next((fields[n] for n in names if fields.get(n)), "")


def _citation(entry):
    """Flatten raw Zotero fields into the citation shape the desk renders and exports."""
    import re
    fields = entry.pop("fields")
    date = fields.get("date") or ""
    # Zotero stores dates as "2020-03-00 March 2020": a sortable part, then the date as typed.
    typed = date.split(" ", 1)[1] if re.match(r"^\d{4}-\d{2}-\d{2} ", date) else date
    year = re.search(r"\b(\d{4})\b", date)
    entry.update({
        "title": fields.get("title") or "",
        "short_title": fields.get("shortTitle") or "",
        "date": typed,
        "year": int(year.group(1)) if year else None,
        "container": _first(fields, "publicationTitle", "bookTitle", "proceedingsTitle", "websiteTitle", "blogTitle"),
        "volume": fields.get("volume") or "",
        "issue": fields.get("issue") or "",
        "pages": fields.get("pages") or "",
        "publisher": _first(fields, "publisher", "institution", "university"),
        "place": fields.get("place") or "",
        "edition": fields.get("edition") or "",
        "report_number": fields.get("reportNumber") or "",
        "thesis_type": fields.get("thesisType") or "",
        "doi": fields.get("DOI") or "",
        "isbn": fields.get("ISBN") or "",
        "url": fields.get("url") or "",
    })
    return entry
