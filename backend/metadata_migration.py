"""
Migrate ChromaDB metadata from legacy format to current format.
Updates metadata in-place without re-embedding documents.
"""

import re
import time
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class MetadataMigration:
    """Migrate ChromaDB metadata to current format."""
    
    def __init__(self, chroma_client, zotero_library):
        self.chroma = chroma_client
        self.zlib = zotero_library
        self.progress = {
            "total_chunks": 0,
            "processed_chunks": 0,
            "updated_chunks": 0,
            "failed_chunks": 0,
            "start_time": None,
            "items_processed": set(),
        }
    
    # Chroma get() with offset is a SQL LIMIT/OFFSET; one page of metadata at a time.
    PAGE_SIZE = 10_000

    def migrate_all_metadata(self, batch_size: int = 1000) -> Dict[str, Any]:
        """
        Migrate all metadata in ChromaDB to current format.

        The Zotero library is read once into a dict keyed by item id; Chroma is
        paged so memory stays bounded on large libraries (issue #86).

        Args:
            batch_size: Number of chunks to update per ChromaDB write.

        Returns:
            Migration summary with counts and errors.
        """
        logger.info("Starting metadata migration...")
        self.progress["start_time"] = time.time()

        cache: Dict[str, Dict] = {}
        offset = 0
        while True:
            page = self.chroma.collection.get(
                limit=self.PAGE_SIZE, offset=offset, include=['metadatas']
            )
            chunk_ids = page.get('ids', [])
            metadatas = page.get('metadatas', [])
            if not chunk_ids:
                break
            self.progress["total_chunks"] += len(chunk_ids)
            for i in range(0, len(chunk_ids), batch_size):
                self._migrate_batch(chunk_ids[i:i + batch_size], metadatas[i:i + batch_size], cache)
            logger.info("Migration progress: %d chunks processed", self.progress["processed_chunks"])
            if len(chunk_ids) < self.PAGE_SIZE:
                break
            offset += len(chunk_ids)

        if self.progress["total_chunks"] == 0:
            logger.warning("No chunks found in collection!")

        elapsed = time.time() - self.progress["start_time"]
        summary = {
            "total_chunks": self.progress["total_chunks"],
            "updated_chunks": self.progress["updated_chunks"],
            "failed_chunks": self.progress["failed_chunks"],
            "unique_items": len(self.progress["items_processed"]),
            "elapsed_seconds": int(elapsed),
            "success": self.progress["failed_chunks"] == 0,
        }
        logger.info(f"Migration complete: {summary}")
        return summary

    def _library_by_item_id(self) -> Dict[str, Any]:
        """Read the Zotero library once and key it by item id.

        The previous version re-read the whole library for every item and
        then took the first row regardless of id, so "Sync Metadata" stamped
        every chunk with the first item's title, authors and tags.
        """
        if not hasattr(self, "_library"):
            self._library = {
                str(item.metadata.get("item_id")): item
                for item in self.zlib.search_parent_items_with_pdfs()
            }
        return self._library

    def _fetch_updated_metadata(self, item_id: str) -> Optional[Dict]:
        """Current metadata for one item from Zotero, normalised (year as int
        or None), or None if the item is not in the library."""
        try:
            item = self._library_by_item_id().get(str(item_id))
            if item is None:
                return None
            year_str = item.metadata.get("date", "")
            year_int: Optional[int] = None
            if year_str:
                match = re.search(r'\b(19|20)\d{2}\b', year_str)
                if match:
                    year_int = int(match.group(0))
            return {
                "title":       item.metadata.get("title", ""),
                "authors":     item.metadata.get("authors", ""),
                "tags":        item.metadata.get("tags", ""),
                "collections": item.metadata.get("collections", ""),
                "year":        year_int,
                "item_type":   item.metadata.get("item_type", ""),
            }
        except Exception as e:
            logger.error(f"Failed to fetch metadata for item {item_id}: {e}")
            return None

    def _migrate_batch(
        self,
        chunk_ids: List[str],
        metadatas: List[Dict],
        cache: Dict[str, Dict],
    ):
        """Migrate a batch of chunks.

        When an item's metadata is not already in *cache*, it is fetched from
        Zotero via _fetch_updated_metadata() and stored in *cache* so that
        subsequent chunks from the same item do not trigger a second query.
        """
        updates_needed = []

        for chunk_id, old_meta in zip(chunk_ids, metadatas):
            try:
                item_id = str(old_meta.get('item_id', ''))
                if not item_id:
                    logger.warning(f"Chunk {chunk_id} has no item_id, skipping")
                    self.progress["failed_chunks"] += 1
                    self.progress["processed_chunks"] += 1
                    continue

                # Populate cache lazily on first encounter of this item_id
                if item_id not in cache:
                    fetched = self._fetch_updated_metadata(item_id)
                    if fetched is None:
                        logger.warning(f"Could not find metadata for item {item_id} in cache")
                        self.progress["failed_chunks"] += 1
                        self.progress["processed_chunks"] += 1
                        continue
                    cache[item_id] = fetched
                    self.chroma.upsert_item(item_id, fetched)  # the item table the scope filters read

                updated_item_meta = cache[item_id]
                
                # Build new metadata dict (preserve chunk-specific fields)
                new_meta = {
                    "item_id": int(item_id) if item_id.isdigit() else item_id,
                    "chunk_idx": int(old_meta.get("chunk_idx", 0)),
                    "page": int(old_meta.get("page", 0)),
                    "pdf_path": old_meta.get("pdf_path", ""),
                    
                    # Updated fields from Zotero
                    "title": updated_item_meta.get("title", ""),
                    "authors": updated_item_meta.get("authors", ""),
                    "tags": updated_item_meta.get("tags") or "",  # Don't store None - ChromaDB strips it
                    "collections": updated_item_meta.get("collections") or "",  # Don't store None
                    "year": updated_item_meta.get("year"),  # Integer or None - but ChromaDB may strip None
                    "item_type": updated_item_meta.get("item_type", ""),
                }
                
                # CRITICAL: ChromaDB strips None values, so we need to handle that
                # For year, if it's None, we should store it as -1 to preserve the key
                if new_meta["year"] is None:
                    new_meta["year"] = -1  # Sentinel value for "no year"
                
                # Check if update is actually needed
                if self._needs_update(old_meta, new_meta):
                    updates_needed.append((chunk_id, new_meta))
                    self.progress["updated_chunks"] += 1
                
                self.progress["processed_chunks"] += 1
                self.progress["items_processed"].add(item_id)
                
            except Exception as e:
                logger.error(f"Error processing chunk {chunk_id}: {e}")
                self.progress["failed_chunks"] += 1
                self.progress["processed_chunks"] += 1
        
        # Apply updates as a batch
        if updates_needed:
            logger.info(f"Applying {len(updates_needed)} updates to ChromaDB")
            self._apply_metadata_updates(updates_needed)
    
    def _needs_update(self, old_meta: Dict, new_meta: Dict) -> bool:
        """Check if metadata actually needs updating."""
        # Check if year format changed (string -> int or None)
        old_year = old_meta.get('year')
        new_year = new_meta.get('year')
        
        # Year needs update if it's currently a string (including empty strings)
        # and needs to be an int or None
        if isinstance(old_year, str):
            # Old format: year as string, new format: year as int or None
            if isinstance(new_year, int) or new_year is None:
                return True
        
        # If old year is None but new year exists (shouldn't happen in v1, but be safe)
        if old_year is None and isinstance(new_year, int):
            return True
        
        # Check if tags/collections content changed (not just existence)
        if old_meta.get('tags', '') != new_meta.get('tags', ''):
            return True
        if old_meta.get('collections', '') != new_meta.get('collections', ''):
            return True
        
        # Check if item_type is missing (new field)
        if 'item_type' not in old_meta and new_meta.get('item_type'):
            return True
        
        return False
    
    def _apply_metadata_updates(self, updates: List[tuple]):
        """Apply metadata updates to ChromaDB."""
        try:
            chunk_ids = [update[0] for update in updates]
            new_metadatas = [update[1] for update in updates]
            
            # ChromaDB update operation
            self.chroma.collection.update(
                ids=chunk_ids,
                metadatas=new_metadatas,
            )
            
            logger.debug(f"Updated {len(chunk_ids)} chunks")
            
        except Exception as e:
            logger.error(f"Error applying metadata updates: {e}")
            raise


def run_migration_cli(chroma_client, zotero_library):
    """Run migration from command line."""
    print("=" * 60)
    print("ChromaDB Metadata Migration Tool")
    print("=" * 60)
    print("\nThis will update metadata format to enable filtering features.")
    print("No re-embedding needed - this only updates metadata fields.")
    print("\nEstimated time: 5-10 minutes for typical library (1000-5000 items)")
    
    response = input("\nProceed with migration? (yes/no): ")
    
    if response.lower() != 'yes':
        print("Migration cancelled.")
        return
    
    migration = MetadataMigration(chroma_client, zotero_library)
    
    print("\n🔄 Starting migration...")
    summary = migration.migrate_all_metadata()
    
    print("\n" + "=" * 60)
    print("Migration Complete!")
    print("=" * 60)
    print(f"Total chunks:   {summary['total_chunks']}")
    print(f"Updated:        {summary['updated_chunks']}")
    print(f"Failed:         {summary['failed_chunks']}")
    print(f"Unique items:   {summary['unique_items']}")
    print(f"Time elapsed:   {summary['elapsed_seconds']}s")
    
    if summary['success']:
        print("\n✅ Migration successful! Metadata filtering is now enabled.")
    else:
        print(f"\n⚠️ Migration completed with {summary['failed_chunks']} errors.")
        print("   Check logs for details.")
