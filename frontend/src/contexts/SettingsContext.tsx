import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { apiFetch, BACKEND_BACK } from '../api/client';
import type { SettingsEdits } from './settingsEdits';

export interface ProviderCredentials {
  api_key?: string;
  base_url?: string;
  [key: string]: string | undefined;
}

export interface ProviderConfig {
  enabled: boolean;
  credentials: ProviderCredentials;
}

export interface ProviderInfo {
  id: string;
  label: string;
  default_model: string;
  supports_streaming: boolean;
  requires_api_key: boolean;
}

export interface ModelInfo {
  id: string;
  name: string;
  description?: string;
  context_length?: number;
}

export interface Settings {
  activeProviderId: string;
  activeModel: string;
  embeddingModel: string;
  zoteroPath: string;
  pdfStoragePath?: string;
  chromaPath: string;
  providers: Record<string, ProviderConfig>;
  showSystemNotification?: boolean;
  playSoundNotification?: boolean;
  maxSources?: number;
  excludedCollections?: string[];
  excludedTags?: string[];
  excludedItemTypes?: string[];
  theme?: 'light' | 'dark';
  /** 'desk' (the reference desk, default) or 'chat' (the chat). */
  interfaceMode?: 'desk' | 'chat';
  /** The desk clerk's jobs (backend/clerk_jobs.py); each needs a model and falls back without one. */
  deskReadQuery?: boolean;
  deskReadTimeout?: number;
  deskAlsoTry?: boolean;
  deskThemes?: boolean;
  /** Let the clerk use a cloud provider (queries and passages are sent to it). Off by default. */
  deskClerkCloud?: boolean;
}

interface SettingsContextType {
  settings: Settings;
  updateSettings: (changes: SettingsEdits) => Promise<void>;
  loading: boolean;
  /** The saved settings could not be read: `settings` holds the defaults. */
  loadFailed: boolean;
  error: string | null;
  clearError: () => void;
  availableProviders: ProviderInfo[];
}

const defaultSettings: Settings = {
  activeProviderId: 'ollama',
  activeModel: '',
  embeddingModel: 'bge-base',
  zoteroPath: '',
  pdfStoragePath: '',
  chromaPath: '',
  showSystemNotification: true,
  playSoundNotification: false,
  maxSources: 0,
  excludedCollections: [],
  excludedTags: [],
  excludedItemTypes: [],
  theme: 'light',
  interfaceMode: 'desk',
  providers: {
    ollama: {
      enabled: true,
      credentials: {
        base_url: 'http://localhost:11434'
      }
    },
    openai: {
      enabled: false,
      credentials: { api_key: '' }
    },
    anthropic: {
      enabled: false,
      credentials: { api_key: '' }
    },
    mistral: {
      enabled: false,
      credentials: { api_key: '' }
    },
    google: {
      enabled: false,
      credentials: { api_key: '' }
    },
    groq: {
      enabled: false,
      credentials: { api_key: '' }
    },
    openrouter: {
      enabled: false,
      credentials: { api_key: '' }
    },
    github_models: {
      enabled: false,
      credentials: { api_key: '' }
    }
  }
};

// The backend's file may predate a provider.
const withDefaults = (data: Partial<Settings>): Settings => ({
  ...defaultSettings,
  ...data,
  providers: { ...defaultSettings.providers, ...(data.providers || {}) },
});

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export const SettingsProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [availableProviders, setAvailableProviders] = useState<ProviderInfo[]>([]);

  const [loadFailed, setLoadFailed] = useState(false);

  // Load available providers from backend
  const loadProviders = async () => {
    try {
      const response = await apiFetch('/api/providers');
      const data = await response.json();
      setAvailableProviders(data.providers || []);
    } catch (err) {
      console.error('Failed to load providers:', err);
    }
  };

  // Never sets loading: a retry must not unmount the app under what the user is typing.
  const loadSettings = async () => {
    try {
      const response = await apiFetch('/api/settings');
      setSettings(withDefaults(await response.json()));
      setLoadFailed(false);
      setError(null);
    } catch (err) {
      console.error('Failed to load settings:', err);
      setLoadFailed(true);
      setError(err instanceof Error ? err.message : 'Your settings could not be read.');
    } finally {
      setLoading(false);
    }
  };

  // Load settings from backend on mount
  useEffect(() => {
    loadSettings();
    loadProviders();
  }, []);

  // A failed load tries again until it works.
  useEffect(() => {
    if (!loadFailed) return;
    const retry = () => {
      loadSettings();
      loadProviders();
    };
    window.addEventListener(BACKEND_BACK, retry);
    const timer = window.setInterval(retry, 5000); // a 500 is no network failure, so no event follows it
    return () => {
      window.removeEventListener(BACKEND_BACK, retry);
      window.clearInterval(timer);
    };
  }, [loadFailed]);

  // Apply the selected theme to the document root (drives [data-theme="dark"] CSS)
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', settings.theme === 'dark' ? 'dark' : 'light');
  }, [settings.theme]);

  // Sends only what changed: the backend merges by key, and a whole object from
  // this render could undo a save in flight or write the defaults over a failed load.
  const updateSettings = async (changes: SettingsEdits) => {
    try {
      setError(null);
      await apiFetch('/api/settings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(changes),
      });

      // After saving, reload settings to get the masked versions
      const reloadResponse = await apiFetch('/api/settings');
      setSettings(withDefaults(await reloadResponse.json()));
      setLoadFailed(false);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to save settings';
      setError(errorMessage);
      throw err;
    }
  };

  return (
    <SettingsContext.Provider value={{ settings, updateSettings, loading, loadFailed, error, clearError: () => setError(null), availableProviders }}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = (): SettingsContextType => {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
};
