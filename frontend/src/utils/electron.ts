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
  // Backend configuration
  getBackendConfig: () => Promise<{ backendUrl: string }>;
  checkBackendHealth: () => Promise<{ healthy: boolean; status?: number; error?: string }>;
  
  // App information
  getAppVersion: () => Promise<string>;
  getPlatform: () => Promise<string>;
  
  // External links
  openExternal: (url: string) => Promise<void>;
  
  // Auto-updater events
  onUpdateChecking: (callback: () => void) => void;
  onUpdateAvailable: (callback: (info: UpdateInfo) => void) => void;
  onUpdateNotAvailable: (callback: (info: { version: string }) => void) => void;
  onUpdateDownloadProgress: (callback: (progress: DownloadProgress) => void) => void;
  onUpdateDownloaded: (callback: (info: UpdateInfo) => void) => void;
  onUpdateError: (callback: (error: { message: string }) => void) => void;
  
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

/**
 * Get the backend URL
 * In Electron: uses the backend spawned by main process
 * In web: uses the configured URL or defaults to localhost:8000
 */
export async function getBackendUrl(): Promise<string> {
  const electron = getElectronAPI();
  
  if (electron) {
    try {
      const config = await electron.getBackendConfig();
      return config.backendUrl;
    } catch (error) {
      console.error('Failed to get backend config from Electron:', error);
    }
  }
  
  // Default to web configuration
  return import.meta.env.VITE_API_URL || 'http://localhost:8000';
}

/**
 * Check backend health
 */
export async function checkBackendHealth(): Promise<boolean> {
  const electron = getElectronAPI();
  
  if (electron) {
    try {
      const health = await electron.checkBackendHealth();
      return health.healthy;
    } catch (error) {
      console.error('Failed to check backend health:', error);
      return false;
    }
  }
  
  // Web fallback: check directly
  try {
    const backendUrl = await getBackendUrl();
    const response = await fetch(`${backendUrl}/`, { 
      method: 'GET',
      signal: AbortSignal.timeout(2000)
    });
    return response.ok;
  } catch (error) {
    return false;
  }
}

/**
 * Get app version
 */
export async function getAppVersion(): Promise<string | null> {
  const electron = getElectronAPI();
  
  if (electron) {
    try {
      return await electron.getAppVersion();
    } catch (error) {
      console.error('Failed to get app version:', error);
    }
  }
  
  return null;
}

/**
 * Get platform
 */
export async function getPlatform(): Promise<string | null> {
  const electron = getElectronAPI();
  
  if (electron) {
    try {
      return await electron.getPlatform();
    } catch (error) {
      console.error('Failed to get platform:', error);
    }
  }
  
  return null;
}

/**
 * Open a URL in the system browser
 */
export async function openExternal(url: string): Promise<void> {
  const electron = getElectronAPI();
  
  if (electron) {
    try {
      await electron.openExternal(url);
      return;
    } catch (error) {
      console.error('Failed to open external URL:', error);
    }
  }
  
  // Web fallback
  window.open(url, '_blank', 'noopener,noreferrer');
}

/**
 * Setup auto-update listeners (Electron only)
 */
export function setupAutoUpdateListeners(callbacks: {
  onUpdateAvailable?: (info: { version: string; releaseNotes?: string }) => void;
  onUpdateDownloadProgress?: (progress: { percent: number; transferred: number; total: number }) => void;
  onUpdateDownloaded?: (info: { version: string }) => void;
}): void {
  const electron = getElectronAPI();
  
  if (!electron) {
    console.log('Auto-update not available (not running in Electron)');
    return;
  }
  
  if (callbacks.onUpdateAvailable) {
    electron.onUpdateAvailable(callbacks.onUpdateAvailable);
  }
  
  if (callbacks.onUpdateDownloadProgress) {
    electron.onUpdateDownloadProgress(callbacks.onUpdateDownloadProgress);
  }
  
  if (callbacks.onUpdateDownloaded) {
    electron.onUpdateDownloaded(callbacks.onUpdateDownloaded);
  }
}

/**
 * Download an available update (Electron only)
 */
export async function downloadUpdate(): Promise<{ success: boolean; error?: string }> {
  const electron = getElectronAPI();
  
  if (!electron) {
    return { success: false, error: 'Not running in Electron' };
  }
  
  try {
    return await electron.downloadUpdate();
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * Install a downloaded update and restart (Electron only)
 */
export function installUpdate(): void {
  const electron = getElectronAPI();
  
  if (!electron) {
    console.error('Cannot install update: not running in Electron');
    return;
  }
  
  electron.installUpdate();
}

// TypeScript type declarations
declare global {
  interface Window {
    electron?: ElectronAPI;
  }
}
