import { useState, useEffect, useCallback } from 'react';

interface UpdateInfo {
  version: string;
  releaseNotes?: string;
}

interface DownloadProgress {
  percent: number;
  transferred: number;
  total: number;
  bytesPerSecond?: number;
}

export type UpdateStatus = 
  | 'idle' 
  | 'checking' 
  | 'available' 
  | 'not-available' 
  | 'downloading' 
  | 'downloaded' 
  | 'error';

interface UseAppUpdaterReturn {
  status: UpdateStatus;
  updateInfo: UpdateInfo | null;
  downloadProgress: DownloadProgress | null;
  error: string | null;
  currentVersion: string;
  checkForUpdates: () => Promise<void>;
  downloadUpdate: () => Promise<void>;
  installUpdate: () => Promise<void>;
}

/**
 * Hook to manage app updates via Electron's auto-updater
 */
export function useAppUpdater(): UseAppUpdaterReturn {
  const [status, setStatus] = useState<UpdateStatus>('idle');
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<DownloadProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentVersion, setCurrentVersion] = useState<string>('');

  // Load current version and update status on mount
  useEffect(() => {
    const loadInitialState = async () => {
      if (!window.electron) return;

      try {
        const version = await window.electron.getAppVersion();
        setCurrentVersion(version);

        const updateStatus = await window.electron.getUpdateStatus();
        if (updateStatus.updateDownloaded) {
          setStatus('downloaded');
          setUpdateInfo(updateStatus.updateInfo);
        } else if (updateStatus.updateAvailable) {
          setStatus('available');
          setUpdateInfo(updateStatus.updateInfo);
        }
      } catch (err) {
        console.error('Failed to load initial update state:', err);
      }
    };

    loadInitialState();
  }, []);

  // Set up event listeners
  useEffect(() => {
    if (!window.electron) return;

    const unsubscribers = [
      // Checking for update
      window.electron.onUpdateChecking(() => {
        setStatus('checking');
        setError(null);
        setDownloadProgress(null);
      }),

      // Update available
      window.electron.onUpdateAvailable((info: UpdateInfo) => {
        setStatus('available');
        setUpdateInfo(info);
        setError(null);
      }),

      // No update available
      window.electron.onUpdateNotAvailable(() => {
        setStatus('not-available');
        setUpdateInfo(null);
        setError(null);
      }),

      // Download progress
      window.electron.onUpdateDownloadProgress((progress: DownloadProgress) => {
        setStatus('downloading');
        setDownloadProgress(progress);
        setError(null);
      }),

      // Update downloaded
      window.electron.onUpdateDownloaded((info: UpdateInfo) => {
        setStatus('downloaded');
        setUpdateInfo(info);
        setDownloadProgress(null);
        setError(null);
      }),

      // Update error
      window.electron.onUpdateError((err: { message: string }) => {
        setStatus('error');
        setError(err.message);
        setDownloadProgress(null);
      }),
    ];

    return () => unsubscribers.forEach((unsubscribe) => unsubscribe());
  }, []);

  const checkForUpdates = useCallback(async () => {
    if (!window.electron) {
      setError('Updates are not available in this environment');
      return;
    }

    try {
      setStatus('checking');
      setError(null);
      
      const result = await window.electron.checkForUpdates();
      
      if (!result.success) {
        setStatus('error');
        setError(result.error || 'Failed to check for updates');
      }
      // Status will be updated by event listeners
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Failed to check for updates');
    }
  }, []);

  const downloadUpdate = useCallback(async () => {
    if (!window.electron) {
      setError('Updates are not available in this environment');
      return;
    }

    try {
      setStatus('downloading');
      setError(null);
      
      const result = await window.electron.downloadUpdate();
      
      if (!result.success) {
        setStatus('error');
        setError(result.error || 'Failed to download update');
      }
      // Status will be updated by event listeners
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Failed to download update');
    }
  }, []);

  const installUpdate = useCallback(async () => {
    if (!window.electron) {
      setError('Updates are not available in this environment');
      return;
    }

    try {
      const result = await window.electron.installUpdate();
      
      if (!result.success) {
        setError(result.error || 'Failed to install update');
      }
      // App will quit and restart after this
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to install update');
    }
  }, []);

  return {
    status,
    updateInfo,
    downloadProgress,
    error,
    currentVersion,
    checkForUpdates,
    downloadUpdate,
    installUpdate,
  };
}
