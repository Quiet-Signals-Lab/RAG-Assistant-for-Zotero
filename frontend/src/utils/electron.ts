/**
 * Electron integration utilities
 * 
 * Provides helper functions to detect if running in Electron
 * and access Electron APIs safely.
 */

// Type definitions for Electron API exposed via preload
export interface UpdateInfo {
  version: string;
  releaseNotes?: string;
}

export interface DownloadProgress {
  percent: number;
  transferred: number;
  total: number;
  bytesPerSecond?: number;
}

export interface UpdateStatus {
  updateAvailable: boolean;
  updateDownloaded: boolean;
  updateInfo: UpdateInfo | null;
  currentVersion: string;
}

export interface ElectronAPI {
  // App information
  getAppVersion: () => Promise<string>;

  // External links
  openExternal: (url: string) => Promise<void>;

  // Auto-updater events; each returns a function that unsubscribes
  onUpdateChecking: (callback: () => void) => () => void;
  onUpdateAvailable: (callback: (info: UpdateInfo) => void) => () => void;
  onUpdateNotAvailable: (callback: (info: { version: string }) => void) => () => void;
  onUpdateDownloadProgress: (callback: (progress: DownloadProgress) => void) => () => void;
  onUpdateDownloaded: (callback: (info: UpdateInfo) => void) => () => void;
  onUpdateError: (callback: (error: { message: string }) => void) => () => void;

  // Auto-updater actions
  checkForUpdates: () => Promise<{ success: boolean; updateInfo?: any; error?: string }>;
  downloadUpdate: () => Promise<{ success: boolean; error?: string }>;
  installUpdate: () => Promise<{ success: boolean; error?: string }>;
  getUpdateStatus: () => Promise<UpdateStatus>;
}

/**
 * Check if the app is running inside Electron
 */
export function isElectron(): boolean {
  return typeof window !== 'undefined' && window.electron !== undefined;
}

/**
 * Get the Electron API (if available)
 */
export function getElectronAPI(): ElectronAPI | null {
  if (isElectron() && window.electron) {
    return window.electron;
  }
  return null;
}

// TypeScript type declarations
declare global {
  interface Window {
    electron?: ElectronAPI;
  }
}
