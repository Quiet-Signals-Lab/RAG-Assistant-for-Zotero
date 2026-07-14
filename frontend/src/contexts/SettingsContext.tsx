import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { apiFetch } from '../api/client';

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
}

interface SettingsContextType {
  settings: Settings;
  updateSettings: (newSettings: Partial<Settings>) => Promise<void>;
  loading: boolean;
  error: string | null;
  availableProviders: ProviderInfo[];
  loadProviders: () => Promise<void>;
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

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export const SettingsProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [availableProviders, setAvailableProviders] = useState<ProviderInfo[]>([]);

  // Load available providers from backend
  const loadProviders = async () => {
    try {
      const response = await apiFetch('/api/providers');
      if (response.ok) {
        const data = await response.json();
        setAvailableProviders(data.providers || []);
      }
    } catch (err) {
      console.error('Failed to load providers:', err);
    }
  };

  // Load settings from backend on mount
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const response = await apiFetch('/api/settings');
        if (response.ok) {
          const text = await response.text();
          try {
            const data = JSON.parse(text);
            
            // Merge with defaults to ensure all providers exist
            const mergedSettings = {
              ...defaultSettings,
              ...data,
              providers: {
                ...defaultSettings.providers,
                ...(data.providers || {})
              }
            };
            
            setSettings(mergedSettings);
          } catch (parseErr) {
            console.error('Failed to parse settings JSON:', parseErr);
            setError('Failed to parse settings. Using defaults.');
            setSettings(defaultSettings);
          }
        } else {
          console.error('Settings request failed:', response.status);
          setError('Failed to load settings from server');
        }
      } catch (err) {
        console.error('Failed to load settings:', err);
        setError('Failed to load settings');
      } finally {
        setLoading(false);
      }
    };

    loadSettings();
    loadProviders();
  }, []);

  // Apply the selected theme to the document root (drives [data-theme="dark"] CSS)
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', settings.theme === 'dark' ? 'dark' : 'light');
  }, [settings.theme]);

  const updateSettings = async (newSettings: Partial<Settings>) => {
    try {
      setError(null);
      const updatedSettings = { ...settings, ...newSettings };
      
      const response = await apiFetch('/api/settings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updatedSettings),
      });

      if (!response.ok) {
        throw new Error('Failed to save settings');
      }

      const result = await response.json();
      
      // After saving, reload settings to get the masked versions
      const reloadResponse = await apiFetch('/api/settings');
      if (reloadResponse.ok) {
        const data = await reloadResponse.json();
        setSettings(data);
      } else {
        // If reload fails, still update local state
        setSettings(updatedSettings);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to save settings';
      setError(errorMessage);
      throw err;
    }
  };

  return (
    <SettingsContext.Provider value={{ settings, updateSettings, loading, error, availableProviders, loadProviders }}>
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
