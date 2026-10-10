/**
 * Utility functions for interacting with Zotero via URI schemes
 */

import { apiFetch } from '../api/client';
import { getElectronAPI } from './electron';

/**
 * Build a zotero://select URI to open and select an item in Zotero
 * @param itemKey - The Zotero item key
 * @param groupId - Optional group ID for group libraries
 * @returns The zotero:// URI or null if itemKey is missing
 */
export function buildZoteroSelectUri(
  itemKey?: string | number | null,
  groupId?: string | number | null
): string | null {
  if (!itemKey) return null;
  const key = encodeURIComponent(String(itemKey));
  if (groupId) {
    return `zotero://select/groups/${encodeURIComponent(String(groupId))}/items/${key}`;
  }
  return `zotero://select/library/items/${key}`;
}

/**
 * Build a zotero://open-pdf URI to open a PDF in Zotero's PDF reader
 * @param itemKey - The Zotero item key
 * @param page - Optional page number to open to
 * @param groupId - Optional group ID for group libraries
 * @returns The zotero:// URI or null if itemKey is missing
 */
export function buildZoteroOpenPdfUri(
  itemKey?: string | number | null,
  page?: number | string | null,
  groupId?: string | number | null
): string | null {
  if (!itemKey) return null;
  const key = encodeURIComponent(String(itemKey));
  // Zotero 7 expects the newer form with /library/
  let uri = groupId
    ? `zotero://open-pdf/groups/${encodeURIComponent(String(groupId))}/items/${key}`
    : `zotero://open-pdf/library/items/${key}`;
  
  const params: string[] = [];
  if (page != null && String(page).trim() !== "") {
    params.push(`page=${encodeURIComponent(String(page))}`);
  }
  if (params.length) {
    uri += `?${params.join("&")}`;
  }
  return uri;
}

/**
 * Hand a zotero:// URI to Zotero. In the desktop app this goes through the main
 * process, which only lets "select" and "open-pdf" links through.
 * @returns false when there was no URI to open
 */
export function tryOpenZoteroUri(uri: string | null): boolean {
  if (!uri) return false;
  const electron = getElectronAPI();
  if (electron) {
    void electron.openExternal(uri);
    return true;
  }
  window.location.href = uri;
  return true;
}

/**
 * Open a local PDF file via the backend /open_pdf endpoint
 * This uses the system's default PDF viewer
 * @param pdfPath - The local file path to the PDF
 * @returns Promise that resolves if successful, rejects with error message if failed
 */
export async function openLocalPdf(pdfPath: string): Promise<void> {
  if (!pdfPath) {
    throw new Error("No PDF path provided");
  }
  
  try {
    await apiFetch("/api/open_pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pdf_path: pdfPath }),
    });
  } catch (e) {
    console.error("Failed to open PDF:", e);
    throw new Error(e instanceof Error ? e.message : "Failed to open PDF");
  }
}
