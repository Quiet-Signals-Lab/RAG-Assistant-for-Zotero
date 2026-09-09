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
    
    def close(self):
        """Close thread-local connections. Call this on shutdown."""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

