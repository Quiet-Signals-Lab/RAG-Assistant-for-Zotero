/**
 * Electron Preload Script
 *
 * Responsibilities:
 * - Bridge between main process and renderer process
 * - Expose safe APIs to the frontend via contextBridge
 * - Handle IPC communication
 *
 * This script runs in a sandboxed context with access to both Node.js
 * and DOM APIs, but uses contextBridge to safely expose only what's needed.
 * The API's type lives in frontend/src/utils/electron.ts.
 */

import { contextBridge, ipcRenderer } from 'electron';

// Returns an unsubscribe: the listening hook is remounted on every Settings visit
function subscribe(channel: string, callback: (payload: any) => void): () => void {
  const listener = (_event: unknown, payload: any) => callback(payload);
  ipcRenderer.on(channel, listener);
  return () => {
    ipcRenderer.removeListener(channel, listener);
  };
}

// Expose the API to the renderer process
contextBridge.exposeInMainWorld('electron', {
  // App information
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),

  // External links
  openExternal: (url: string) => ipcRenderer.invoke('open-external', url),

  // Auto-updater event listeners
  onUpdateChecking: (callback: () => void) => subscribe('update-checking', () => callback()),

  onUpdateAvailable: (callback: (info: any) => void) => subscribe('update-available', callback),

  onUpdateNotAvailable: (callback: (info: any) => void) => subscribe('update-not-available', callback),

  onUpdateDownloadProgress: (callback: (progress: any) => void) => subscribe('update-download-progress', callback),

  onUpdateDownloaded: (callback: (info: any) => void) => subscribe('update-downloaded', callback),

  onUpdateError: (callback: (error: any) => void) => subscribe('update-error', callback),

  // Auto-updater actions
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),

  downloadUpdate: () => ipcRenderer.invoke('download-update'),

  installUpdate: () => ipcRenderer.invoke('install-update'),

  getUpdateStatus: () => ipcRenderer.invoke('get-update-status'),
});
