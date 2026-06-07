# Release Notes - v0.1.11

**Release Date**: December 31, 2025

##  Focus: Sync Diagnostics & Error Reporting

This release dramatically improves visibility into indexing failures and provides powerful diagnostic tools to troubleshoot sync issues.

##  New Features

### Comprehensive Sync Diagnostics
- **Skip Reasons Tracking**: All indexing failures are now tracked with detailed reasons
- **Real-time Error Display**: Orange warning boxes show skipped items during indexing
- **Diagnostic Endpoint**: New `/diagnose_unindexed` API endpoint analyzes stuck items
- **Diagnostic Button**: " Diagnose Sync Issues" button in sync menu for instant analysis

### Enhanced Error Logging
- Detailed console logging for every indexing operation (SKIPPED/ERROR/SUCCESS)
- Comprehensive indexing summaries with success/failure counts
- Specific error messages for each failure type:
  - Missing PDF files with full paths
  - PDF extraction failures with exception details
  - Empty/corrupt PDFs
  - Embedding generation errors
  - ChromaDB storage failures

### Improved User Experience
- Visual feedback during indexing shows skip reasons in real-time
- First 3 skip reasons displayed inline, with count of additional failures
- Browser console logging for detailed diagnostics
- Backend terminal output provides complete error traces

##  Bug Fixes

- **Fixed**: Silent indexing failures that caused items to stay in "needs sync" state indefinitely
- **Fixed**: Items marked as "processed" but never actually indexed
- **Fixed**: No visibility into why specific items couldn't be indexed

##  Documentation

- Added comprehensive `SYNC_DIAGNOSTICS.md` guide covering:
  - Root cause analysis of sync issues
  - How to use diagnostic features
  - Common issues and solutions
  - Technical implementation details

##  Technical Improvements

### Backend
- `skip_reasons` array in `index_progress` tracks all failures
- Try-catch blocks around all critical operations
- Detailed error messages with item IDs and context
- Success logging for successfully indexed items
- Final summaries for both full and incremental indexing

### Frontend
- Skip reasons displayed in TopNav during indexing
- Diagnostic button integrated into sync dropdown menu
- Alert with console logging for detailed diagnostics
- Supports both full reindex and incremental sync modes

##  Usage

### Diagnosing Sync Issues

1. **Check Sync Button**: If showing `Sync (N)`, items need indexing
2. **Click Dropdown**: Next to sync button for index options
3. **Run Diagnostics**: Click " Diagnose Sync Issues"
4. **Review Output**: Check browser console (F12) for details
5. **Fix Issues**: Address missing PDFs, permissions, etc.
6. **Re-sync**: Run sync again to verify fixes

### Monitoring Indexing

- **During Indexing**: Watch for orange warning boxes with skip reasons
- **Backend Logs**: Check terminal for detailed SKIPPED/ERROR/SUCCESS messages
- **After Completion**: Review final summary with success/failure counts

##  Common Issues Resolved

The diagnostic tools now help identify:
- Missing PDF attachments
- Inaccessible file paths
- Corrupt or image-only PDFs
- Embedding service issues
- Database storage problems

##  Upgrading

This release is backward compatible. Existing indexes and settings are preserved.

##  Resources

- Full diagnostic guide: `SYNC_DIAGNOSTICS.md`
- API documentation: `/diagnose_unindexed` endpoint
- Issue tracker: [GitHub Issues](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/issues)

---

**Installation**: Download the appropriate installer for your platform from the [releases page](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/tag/v0.1.11).

**Feedback**: Report issues or suggest improvements via [GitHub Issues](https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/issues).
