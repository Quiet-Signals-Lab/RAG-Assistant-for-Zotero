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
 */

import { contextBridge, ipcRenderer } from 'electron';

// Define the API that will be exposed to the renderer
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
  onUpdateAvailable: (callback: (info: { version: string; releaseNotes?: string }) => void) => void;
  onUpdateNotAvailable: (callback: (info: { version: string }) => void) => void;
  onUpdateDownloadProgress: (callback: (progress: { percent: number; transferred: number; total: number; bytesPerSecond?: number }) => void) => void;
  onUpdateDownloaded: (callback: (info: { version: string; releaseNotes?: string }) => void) => void;
  onUpdateError: (callback: (error: { message: string }) => void) => void;
  
  // Auto-updater actions
  checkForUpdates: () => Promise<{ success: boolean; updateInfo?: any; error?: string }>;
  downloadUpdate: () => Promise<{ success: boolean; error?: string }>;
  installUpdate: () => Promise<{ success: boolean; error?: string }>;
  getUpdateStatus: () => Promise<{ updateAvailable: boolean; updateDownloaded: boolean; updateInfo: any; currentVersion: string }>;
}

// Expose the API to the renderer process
contextBridge.exposeInMainWorld('electron', {
  // Backend configuration
  getBackendConfig: () => ipcRenderer.invoke('get-backend-config'),
  
  checkBackendHealth: () => ipcRenderer.invoke('check-backend-health'),
  
  // App information
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  
  getPlatform: () => ipcRenderer.invoke('get-platform'),
  
  // External links
  openExternal: (url: string) => ipcRenderer.invoke('open-external', url),
  
  // Auto-updater event listeners
  onUpdateChecking: (callback: () => void) => {
    ipcRenderer.on('update-checking', () => callback());
  },
  
  onUpdateAvailable: (callback: (info: any) => void) => {
    ipcRenderer.on('update-available', (event, info) => callback(info));
  },
  
  onUpdateNotAvailable: (callback: (info: any) => void) => {
    ipcRenderer.on('update-not-available', (event, info) => callback(info));
  },
  
  onUpdateDownloadProgress: (callback: (progress: any) => void) => {
    ipcRenderer.on('update-download-progress', (event, progress) => callback(progress));
  },
  
  onUpdateDownloaded: (callback: (info: any) => void) => {
    ipcRenderer.on('update-downloaded', (event, info) => callback(info));
  },
  
  onUpdateError: (callback: (error: any) => void) => {
    ipcRenderer.on('update-error', (event, error) => callback(error));
  },
  
  // Auto-updater actions
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  
  downloadUpdate: () => ipcRenderer.invoke('download-update'),
  
  installUpdate: () => ipcRenderer.invoke('install-update'),
  
  getUpdateStatus: () => ipcRenderer.invoke('get-update-status'),
} as ElectronAPI);

// Extend the Window interface for TypeScript
declare global {
  interface Window {
    electron: ElectronAPI;
  }
}
