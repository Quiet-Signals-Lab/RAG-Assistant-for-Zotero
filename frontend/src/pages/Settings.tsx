import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSettings, ModelInfo, ProviderInfo } from '../contexts/SettingsContext';
import { apiFetch } from '../api/client';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import ProfileSelector from '../components/profile/ProfileSelector';
import { useProfile } from '../contexts/ProfileContext';
import { useAppUpdater } from '../hooks/useAppUpdater';
import { isElectron } from '../utils/electron';
import '../styles/settings.css';

const Settings: React.FC = () => {
  const navigate = useNavigate();
  const { settings, updateSettings, loading, availableProviders } = useSettings();
  const { profiles, activeProfile, deleteProfile } = useProfile();
  const [formData, setFormData] = useState(settings);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<Record<string, ModelInfo[]>>({});
  const [loadingModels, setLoadingModels] = useState<Record<string, boolean>>({});
  const [validatingProvider, setValidatingProvider] = useState<string | null>(null);
  const [providerValidation, setProviderValidation] = useState<Record<string, { valid: boolean; message?: string }>>({});
  const [showApiKeys, setShowApiKeys] = useState<Record<string, boolean>>({});
  const [detectedEnvKeys, setDetectedEnvKeys] = useState<Record<string, { detected: boolean; env_var?: string }>>({});
  const [activeTab, setActiveTab] = useState<'general' | 'local' | 'cloud' | 'advanced'>('general');
  
  // Auto-updater hook (only used in Electron)
  const updater = useAppUpdater();

  useEffect(() => {
    setFormData(settings);
  }, [settings]);

  // Detect environment variable API keys on mount
  useEffect(() => {
    const detectKeys = async () => {
      try {
        const response = await apiFetch('/api/detect_api_keys');
        const data = await response.json();
        if (data.detected_keys) {
          setDetectedEnvKeys(data.detected_keys);
        }
      } catch (err) {
        console.error('Failed to detect environment API keys:', err);
      }
    };
    detectKeys();
  }, []);

  const handleInputChange = (field: keyof typeof formData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setSaveSuccess(false);
    setSaveError(null);
  };

  const handleBooleanChange = (field: keyof typeof formData, value: boolean) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setSaveSuccess(false);
    setSaveError(null);
  };

  const handleProviderEnabledChange = (providerId: string, enabled: boolean) => {
    setFormData(prev => ({
      ...prev,
      providers: {
        ...prev.providers,
        [providerId]: {
          ...prev.providers[providerId],
          enabled
        }
      }
    }));
    setSaveSuccess(false);
    setSaveError(null);
  };

  const handleProviderCredentialChange = (providerId: string, key: string, value: string) => {
    setFormData(prev => ({
      ...prev,
      providers: {
        ...prev.providers,
        [providerId]: {
          ...prev.providers[providerId],
          credentials: {
            ...prev.providers[providerId].credentials,
            [key]: value
          }
        }
      }
    }));
    // Clear cached models so they reload with the new credentials/endpoint
    setAvailableModels(prev => { const updated = { ...prev }; delete updated[providerId]; return updated; });
    setSaveSuccess(false);
    setSaveError(null);
  };

  const loadModelsForProvider = async (providerId: string) => {
    setLoadingModels(prev => ({ ...prev, [providerId]: true }));
    try {
      const response = await apiFetch(`/api/providers/${providerId}/models`);
      if (response.ok) {
        const data = await response.json();
        setAvailableModels(prev => ({ ...prev, [providerId]: data.models || [] }));
      }
    } catch (err) {
      console.error(`Failed to load models for ${providerId}:`, err);
    } finally {
      setLoadingModels(prev => ({ ...prev, [providerId]: false }));
    }
  };

  const validateProvider = async (providerId: string) => {
    setValidatingProvider(providerId);
    try {
      // Always validate stored credentials, not form data
      // This avoids issues with masked keys and ensures we test what's actually saved
      const response = await apiFetch(`/api/providers/${providerId}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          credentials: {}
        })
      });
      const data = await response.json();
      setProviderValidation(prev => ({
        ...prev,
        [providerId]: {
          valid: data.valid,
          message: data.error || data.message || data.details || (data.valid ? 'Connection successful' : 'Validation failed')
        }
      }));
      
      // If valid, handle models
      if (data.valid) {
        // For providers that return models in validation response
        if (data.models && data.models.length > 0) {
          console.log(`[Settings] Received ${data.models.length} dynamic models from validation for ${providerId}`);
          setAvailableModels(prev => ({ ...prev, [providerId]: data.models }));
        } else {
          // Otherwise, load models separately
          await loadModelsForProvider(providerId);
        }
      }
    } catch (err) {
      setProviderValidation(prev => ({
        ...prev,
        [providerId]: {
          valid: false,
          message: 'Connection failed'
        }
      }));
    } finally {
      setValidatingProvider(null);
    }
  };

  useEffect(() => {
    // Load models for enabled providers on mount
    Object.entries(formData.providers).forEach(([providerId, config]) => {
      if (config.enabled && !loadingModels[providerId] && !availableModels[providerId]) {
        loadModelsForProvider(providerId);
      }
    });
  }, [formData.providers]);

  const handleSave = async () => {
    try {
      setSaving(true);
      setSaveError(null);
      
      // Filter out masked API keys before saving
      // Masked keys contain • (bullet) characters and shouldn't be saved
      const dataToSave = {
        ...formData,
        providers: { ...formData.providers }
      };
      
      Object.keys(dataToSave.providers).forEach(providerId => {
        const providerData = dataToSave.providers[providerId];
        if (providerData.credentials?.api_key && providerData.credentials.api_key.includes('•')) {
          // Don't send masked key - backend will keep existing key
          dataToSave.providers[providerId] = {
            ...providerData,
            credentials: {
              ...providerData.credentials,
              api_key: settings.providers[providerId]?.credentials?.api_key || ''
            }
          };
        }
      });
      
      await updateSettings(dataToSave);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAndTest = async (providerId: string) => {
    try {
      // First, save the settings
      setSaving(true);
      setSaveError(null);
      
      // Filter out masked API keys before saving
      const dataToSave = {
        ...formData,
        providers: { ...formData.providers }
      };
      
      Object.keys(dataToSave.providers).forEach(pid => {
        const providerData = dataToSave.providers[pid];
        if (providerData.credentials?.api_key && providerData.credentials.api_key.includes('•')) {
          // Don't send masked key - backend will keep existing key
          dataToSave.providers[pid] = {
            ...providerData,
            credentials: {
              ...providerData.credentials,
              api_key: settings.providers[pid]?.credentials?.api_key || ''
            }
          };
        }
      });
      
      await updateSettings(dataToSave);
      setSaving(false);
      
      // Then, validate the provider
      await validateProvider(providerId);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save settings');
      setSaving(false);
    }
  };

  const getProviderInfo = (providerId: string): ProviderInfo | undefined => {
    return availableProviders.find(p => p.id === providerId);
  };

  // Helper to render a provider configuration card
  const renderProviderCard = (provider: ProviderInfo) => {
    const config = formData.providers[provider.id];
    const validation = providerValidation[provider.id];
    const isValidating = validatingProvider === provider.id;

    return (
      <div key={provider.id} className="provider-config-card">
        <div className="provider-header">
          <label className="provider-toggle">
            <input
              type="checkbox"
              checked={config?.enabled || false}
              onChange={(e) => handleProviderEnabledChange(provider.id, e.target.checked)}
            />
            <span className="provider-name">
              {provider.label}
            </span>
          </label>
          {validation && (
            <span className={`provider-status ${validation.valid ? 'valid' : 'invalid'}`}>
              {validation.valid ? ' Connected' : ' ' + validation.message}
            </span>
          )}
        </div>

        {config?.enabled && (
          <div className="provider-credentials">
            {provider.requires_api_key && (
              <div className="settings-field">
                <label className="settings-label" htmlFor={`${provider.id}-api-key`}>
                  {provider.id === 'github_models' ? 'GitHub Token' : 'API Key'}
                  {provider.id === 'google' && (
                    <span style={{ marginLeft: '8px', fontSize: '12px', color: '#ff5722', fontWeight: 'normal' }}>
                      (Unreliable)
                    </span>
                  )}
                  {detectedEnvKeys[provider.id]?.detected && (
                    <span className="env-key-warning" title={`Using ${detectedEnvKeys[provider.id].env_var} from environment`}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ marginLeft: '6px', verticalAlign: 'middle' }}>
                        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" stroke="#ff9800" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="#fff3e0"/>
                        <path d="M12 9v4M12 17h.01" stroke="#ff9800" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                      <span style={{ fontSize: '11px', color: '#ff9800', marginLeft: '4px' }}>From env</span>
                    </span>
                  )}
                </label>
                <div style={{ position: 'relative' }}>
                  <Input
                    id={`${provider.id}-api-key`}
                    type={showApiKeys[provider.id] ? 'text' : 'password'}
                    value={config.credentials.api_key || ''}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      handleProviderCredentialChange(provider.id, 'api_key', e.target.value)
                    }
                    placeholder={provider.id === 'github_models' ? 'Enter GitHub personal access token' : 'Enter API key'}
                    className="settings-input"
                    style={{ paddingRight: '40px' }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKeys(prev => ({ ...prev, [provider.id]: !prev[provider.id] }))}
                    className="api-key-toggle"
                    title={showApiKeys[provider.id] ? 'Hide API key' : 'Show API key'}
                  >
                    {showApiKeys[provider.id] ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24M1 1l22 22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </button>
                </div>
                {['openai', 'mistral', 'groq', 'openrouter', 'github_models'].includes(provider.id) && (
                  <p className="settings-helper-text">
                    {provider.id === 'github_models'
                      ? 'Generate a token at github.com/settings/tokens (no special scopes required). Works with GitHub Copilot subscriptions.'
                      : 'Models are automatically discovered from your API key when you test the connection.'}
                  </p>
                )}
              </div>
            )}
            
            {/* Custom endpoint support for OpenAI-compatible providers */}
            {['openai', 'mistral', 'groq', 'openrouter'].includes(provider.id) && (
              <div className="settings-field">
                <label className="settings-label" htmlFor={`${provider.id}-base-url`}>
                  Custom Endpoint (Optional)
                </label>
                <Input
                  id={`${provider.id}-base-url`}
                  type="text"
                  value={config.credentials.base_url || ''}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    handleProviderCredentialChange(provider.id, 'base_url', e.target.value)
                  }
                  placeholder={
                    provider.id === 'openai' ? 'https://api.openai.com/v1' :
                    provider.id === 'mistral' ? 'https://api.mistral.ai/v1' :
                    provider.id === 'groq' ? 'https://api.groq.com/openai/v1' :
                    'https://openrouter.ai/api/v1'
                  }
                  className="settings-input"
                />
                <p className="settings-helper-text">
                  Leave blank to use the default endpoint. Useful for Azure OpenAI, proxies, or custom deployments.
                </p>
              </div>
            )}
            
            {provider.id === 'ollama' && (
              <div className="settings-field">
                <label className="settings-label" htmlFor="ollama-base-url">
                  Base URL
                </label>
                <Input
                  id="ollama-base-url"
                  type="text"
                  value={config.credentials.base_url || 'http://localhost:11434'}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    handleProviderCredentialChange(provider.id, 'base_url', e.target.value)
                  }
                  className="settings-input"
                />
              </div>
            )}

            {provider.id === 'lmstudio' && (
              <div className="settings-field">
                <label className="settings-label" htmlFor="lmstudio-base-url">
                  Base URL
                </label>
                <Input
                  id="lmstudio-base-url"
                  type="text"
                  value={config.credentials.base_url || 'http://localhost:1234'}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    handleProviderCredentialChange(provider.id, 'base_url', e.target.value)
                  }
                  className="settings-input"
                  placeholder="http://localhost:1234"
                />
                <p className="settings-helper-text">
                  Make sure LM Studio is running and the local server is started.
                </p>
              </div>
            )}

            <Button
              onClick={() => handleSaveAndTest(provider.id)}
              variant="secondary"
              disabled={isValidating || saving}
            >
              {isValidating ? 'Testing...' : saving ? 'Saving...' : 'Save & Test'}
            </Button>
          </div>
        )}
      </div>
    );
  };

  // Filter providers by type
  const localProviders = availableProviders.filter(p => !p.requires_api_key);
  const cloudProviders = availableProviders.filter(p => p.requires_api_key);

  if (loading) {
    return (
      <div className="settings-page">
        <div className="settings-loading">Loading settings...</div>
      </div>
    );
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <button className="settings-back-btn" onClick={() => navigate('/')}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M19 12H5M5 12l7-7M5 12l7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Back
        </button>
        <h1 className="settings-title">Settings</h1>
      </div>

      {/* Tab Navigation */}
      <div className="settings-tabs">
        <button 
          className={`settings-tab ${activeTab === 'general' ? 'active' : ''}`}
          onClick={() => setActiveTab('general')}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2"/>
            <path d="M12 1v6M12 17v6M4.22 4.22l4.24 4.25M15.54 15.54l4.25 4.25M1 12h6M17 12h6M4.22 19.78l4.24-4.25M15.54 8.46l4.25-4.25" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          General
        </button>
        <button 
          className={`settings-tab ${activeTab === 'local' ? 'active' : ''}`}
          onClick={() => setActiveTab('local')}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="2" y="3" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="2"/>
            <path d="M8 21h8M12 17v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          Local Models
        </button>
        <button 
          className={`settings-tab ${activeTab === 'cloud' ? 'active' : ''}`}
          onClick={() => setActiveTab('cloud')}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Cloud Providers
        </button>
        <button 
          className={`settings-tab ${activeTab === 'advanced' ? 'active' : ''}`}
          onClick={() => setActiveTab('advanced')}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Advanced
        </button>
      </div>

      <div className="settings-container">{activeTab === 'general' && (
        <>
        <section className="settings-section">
          <h2 className="settings-section-title">Support & Feedback</h2>
          <p className="settings-section-description">
            Help improve RAG Assistant for Zotero by reporting bugs or supporting the project.
          </p>
          
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginTop: '16px' }}>
            <Button
              onClick={() => window.open('https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/issues/new', '_blank', 'noopener,noreferrer')}
              variant="secondary"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ marginRight: '8px' }}>
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                <path d="M12 8v4M12 16h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              Report a Bug
            </Button>
            
            <Button
              onClick={() => window.open('https://github.com/sponsors/aahepburn', '_blank', 'noopener,noreferrer')}
              variant="secondary"
              style={{ 
                display: 'flex', 
                alignItems: 'center',
                gap: '8px'
              }}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M7.655 14.916L7.648 14.91L7.641 14.903C5.787 13.29 4.328 11.984 3.316 10.781C2.315 9.59 1.8 8.55 1.8 7.5C1.8 5.821 3.021 4.6 4.7 4.6C5.746 4.6 6.77 5.171 7.34 6.025L8 7.015L8.66 6.025C9.23 5.171 10.254 4.6 11.3 4.6C12.979 4.6 14.2 5.821 14.2 7.5C14.2 8.55 13.685 9.59 12.684 10.781C11.672 11.984 10.213 13.29 8.359 14.903L8.352 14.91L8.345 14.916C8.153 15.082 7.847 15.082 7.655 14.916Z" fill="#DB61A2" stroke="#DB61A2" strokeWidth="1.2"/>
              </svg>
              <span style={{ color: '#DB61A2', fontWeight: 500 }}>Sponsor</span>
            </Button>
          </div>
          
          <div className="settings-hint" style={{ marginTop: '12px' }}>
            <strong>Found a bug?</strong> Open an issue on GitHub and include:
            <ul style={{ marginTop: '8px', marginLeft: '20px', lineHeight: '1.6' }}>
              <li>Screenshots of the problem</li>
              <li>Any error messages you see</li>
              <li>Console logs (open Dev Tools with <kbd style={{ padding: '2px 6px', backgroundColor: 'var(--bg-secondary, #e9ecef)', borderRadius: '3px', fontSize: '12px' }}>Cmd+Option+I</kbd> on Mac or <kbd style={{ padding: '2px 6px', backgroundColor: 'var(--bg-secondary, #e9ecef)', borderRadius: '3px', fontSize: '12px' }}>Ctrl+Shift+I</kbd> on Windows/Linux, then copy from the Console tab)</li>
            </ul>
            <strong>Like the app?</strong> Consider sponsoring to support continued development!
          </div>

          <p className="settings-hint" style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border-subtle)', fontSize: '12px' }}>
            © 2025 Alexander Hepburn · Licensed under the{' '}
            <a
              href="https://www.apache.org/licenses/LICENSE-2.0"
              target="_blank"
              rel="noopener noreferrer"
            >
              Apache License 2.0
            </a>
          </p>
        </section>

        <section className="settings-section">
          <h2 className="settings-section-title">Notifications</h2>
          <p className="settings-section-description">
            Configure how you want to be notified when the assistant responds to your questions.
          </p>

          <div className="settings-field">
            <label className="settings-label" style={{ cursor: 'pointer', userSelect: 'none' }}>
              <input
                type="checkbox"
                checked={formData.showSystemNotification ?? true}
                onChange={(e) => handleBooleanChange('showSystemNotification', e.target.checked)}
                style={{ 
                  marginRight: '8px', 
                  width: '18px', 
                  height: '18px', 
                  cursor: 'pointer',
                  accentColor: 'var(--accent)'
                }}
              />
              Show system notification
            </label>
            <p className="settings-hint">
              Display a desktop notification when the assistant finishes responding.
            </p>
          </div>

          <div className="settings-field">
            <label className="settings-label" style={{ cursor: 'pointer', userSelect: 'none' }}>
              <input
                type="checkbox"
                checked={formData.playSoundNotification ?? false}
                onChange={(e) => handleBooleanChange('playSoundNotification', e.target.checked)}
                style={{ 
                  marginRight: '8px', 
                  width: '18px', 
                  height: '18px', 
                  cursor: 'pointer',
                  accentColor: 'var(--accent)'
                }}
              />
              Play sound notification
            </label>
            <p className="settings-hint">
              Play a sound effect when the assistant finishes responding.
            </p>
          </div>
        </section>

        <section className="settings-section">
          <h2 className="settings-section-title">Profile</h2>
          <p className="settings-section-description">
            Manage your user profiles. Each profile has its own settings, chat history, and vector database.
          </p>
          <ProfileSelector />
        </section>

        {/* Updates Section - Only shown in Electron */}
        {isElectron() && (
          <section className="settings-section">
            <h2 className="settings-section-title">Application Updates</h2>
            <p className="settings-section-description">
              Keep your application up to date with the latest features and improvements.
            </p>
            
            <div className="update-status-card">
              <div className="update-info">
                <div className="update-version">
                  <strong>Current Version:</strong> {updater.currentVersion || 'Loading...'}
                </div>
                
                {updater.status === 'idle' && (
                  <div className="update-message">
                    Click "Check for Updates" to see if a new version is available.
                  </div>
                )}
                
                {updater.status === 'checking' && (
                  <div className="update-message checking">
                    <span className="spinner"></span>
                    Checking for updates...
                  </div>
                )}
                
                {updater.status === 'not-available' && (
                  <div className="update-message up-to-date">
                     You're running the latest version
                  </div>
                )}
                
                {updater.status === 'available' && updater.updateInfo && (
                  <div className="update-message available">
                    <strong>Update Available:</strong> Version {updater.updateInfo.version}
                    {updater.updateInfo.releaseNotes && (
                      <div className="release-notes">
                        <details>
                          <summary>Release Notes</summary>
                          <div className="release-notes-content">
                            {updater.updateInfo.releaseNotes}
                          </div>
                        </details>
                      </div>
                    )}
                  </div>
                )}
                
                {updater.status === 'downloading' && updater.downloadProgress && (
                  <div className="update-message downloading">
                    <div className="download-progress">
                      <div className="progress-text">
                        Downloading update... {updater.downloadProgress.percent.toFixed(1)}%
                      </div>
                      <div className="progress-bar">
                        <div 
                          className="progress-fill" 
                          style={{ width: `${updater.downloadProgress.percent}%` }}
                        />
                      </div>
                      <div className="progress-details">
                        {(updater.downloadProgress.transferred / 1024 / 1024).toFixed(1)} MB / 
                        {(updater.downloadProgress.total / 1024 / 1024).toFixed(1)} MB
                      </div>
                    </div>
                  </div>
                )}
                
                {updater.status === 'downloaded' && updater.updateInfo && (
                  <div className="update-message downloaded">
                    <strong> Update Ready to Install</strong>
                    <p>Version {updater.updateInfo.version} has been downloaded and is ready to install.</p>
                    <p className="install-note">
                      The application will restart to complete the installation.
                    </p>
                  </div>
                )}
                
                {updater.status === 'error' && updater.error && (
                  <div className="update-message error">
                    <strong>Error:</strong> {updater.error}
                  </div>
                )}
              </div>
              
              <div className="update-actions">
                {(updater.status === 'idle' || updater.status === 'not-available' || updater.status === 'error') && (
                  <Button
                    onClick={updater.checkForUpdates}
                    variant="secondary"
                  >
                    Check for Updates
                  </Button>
                )}
              </div>
              
              {updater.status === 'available' && updater.updateInfo && (
                <div className="settings-note" style={{ 
                  marginTop: '16px',
                  padding: '16px', 
                  backgroundColor: 'var(--warning-bg, #fff3cd)', 
                  borderLeft: '4px solid var(--warning, #ffc107)', 
                  fontSize: '14px',
                  color: 'var(--text)',
                  lineHeight: '1.6'
                }}>
                  <strong style={{ display: 'block', marginBottom: '8px', fontSize: '15px' }}>
                    ⚠️ Manual Update Required
                  </strong>
                  <p style={{ margin: '0 0 12px 0' }}>
                    Version {updater.updateInfo.version} is available. To update, please download the new release file manually from GitHub Releases.
                  </p>
                  <Button
                    onClick={() => window.electron?.openExternal('https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/latest')}
                    variant="primary"
                    style={{ marginTop: '8px' }}
                  >
                    Download from GitHub Releases →
                  </Button>
                </div>
              )}
              
              <div className="settings-note" style={{ 
                marginTop: '16px',
                padding: '14px', 
                backgroundColor: '#d4edda', 
                borderLeft: '4px solid #28a745', 
                fontSize: '13px',
                color: '#155724',
                borderRadius: '4px'
              }}>
                <strong style={{ display: 'block', marginBottom: '6px' }}>✓ Safe Manual Updates</strong>
                <p style={{ margin: '0 0 8px 0', lineHeight: '1.5' }}>
                  Automatic updates are disabled. When a new version is available, you'll need to download and install it manually from{' '}
                  <a 
                    href="https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    style={{ color: '#0c5d29', textDecoration: 'underline', fontWeight: '500' }}
                  >
                    GitHub Releases
                  </a>.
                </p>
                <p style={{ margin: '0', fontSize: '12px', opacity: '0.9' }}>
                  <strong>Your data is safe:</strong> Profile configurations, API keys, embeddings, and all settings will persist across updates.
                </p>
              </div>
            </div>
          </section>
        )}

        <section className="settings-section">
          <h2 className="settings-section-title">Zotero Configuration</h2>
          <div className="settings-field">
            <label className="settings-label">Zotero Database Path</label>
            <input
              type="text"
              className="settings-input"
              value={formData.zoteroPath}
              onChange={(e) => handleInputChange('zoteroPath', e.target.value)}
              placeholder={navigator.platform.startsWith('Win') ? 'C:\\Users\\YourName\\Zotero\\zotero.sqlite' : (navigator.platform.startsWith('Mac') ? '/Users/YourName/Zotero/zotero.sqlite' : '~/Zotero/zotero.sqlite')}
            />
            <p className="settings-hint">
              Full path to your <code>zotero.sqlite</code> file. This is typically in your Zotero data directory.
            </p>
          </div>
          <div className="settings-field">
            <label className="settings-label">PDF Storage Directory <span style={{ fontWeight: 'normal', opacity: 0.7 }}>(optional)</span></label>
            <input
              type="text"
              className="settings-input"
              value={formData.pdfStoragePath ?? ''}
              onChange={(e) => handleInputChange('pdfStoragePath', e.target.value)}
              placeholder={navigator.platform.startsWith('Win') ? 'C:\\Users\\YourName\\Zotero\\storage' : (navigator.platform.startsWith('Mac') ? '/Users/YourName/Zotero/storage' : '~/Zotero/storage')}
            />
            <p className="settings-hint">
              Path to your Zotero PDF storage folder. Leave blank to use the default location next to the database file.
            </p>
          </div>
        </section>
        </>
      )}

      {activeTab === 'local' && (
        <section className="settings-section">
          <h2 className="settings-section-title">Local Model Providers</h2>
          <p className="settings-section-description">
            Configure local LLM services running on your machine. These don't require API keys or send data externally.
          </p>

          {localProviders.map(provider => renderProviderCard(provider))}
        </section>
      )}

      {activeTab === 'cloud' && (
        <section className="settings-section">
          <h2 className="settings-section-title">Cloud API Providers</h2>
          <p className="settings-section-description">
            Configure external LLM API providers. These require API keys and send requests to external services.
          </p>

          {cloudProviders.map(provider => renderProviderCard(provider))}
        </section>
      )}

      {activeTab === 'advanced' && (
        <section className="settings-section">
          <h2 className="settings-section-title">Retrieval</h2>
          <p className="settings-section-description">
            Control how much evidence the system retrieves from your library for each query.
            By default, the limit is set automatically based on your active model's context window.
          </p>

          <div className="settings-field">
            <label className="settings-label">Evidence snippets per query</label>
            <select
              className="settings-input"
              value={formData.maxSources ?? 0}
              onChange={e => {
                const v = parseInt(e.target.value, 10);
                setFormData(prev => ({ ...prev, maxSources: v }));
                setSaveSuccess(false);
                setSaveError(null);
              }}
            >
              <option value={0}>Auto — scaled to model context window (recommended)</option>
              <option value={4}>4 snippets</option>
              <option value={6}>6 snippets</option>
              <option value={8}>8 snippets</option>
              <option value={10}>10 snippets</option>
              <option value={12}>12 snippets</option>
              <option value={16}>16 snippets</option>
              <option value={20}>20 snippets</option>
              <option value={30}>30 snippets</option>
            </select>
            <p className="settings-hint">
              Each snippet is a relevant passage from your library. Multiple snippets may come from
              the same paper; the number of cited sources shown will typically be lower than this
              value. Increase this if your answers are missing key sources. Local/Ollama models
              default to 6 snippets (conservative) — setting a higher value may cause context
              overflow on small-context models (&lt;16k tokens).
            </p>
          </div>
        </section>
      )}

        <div className="settings-actions">
          {saveSuccess && (
            <div className="settings-success">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Settings saved successfully
            </div>
          )}
          {saveError && (
            <div className="settings-error">
              {saveError}
            </div>
          )}
          <Button 
            onClick={handleSave} 
            disabled={saving}
            variant="primary"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </Button>
          <Button 
            onClick={() => navigate('/')} 
            variant="secondary"
          >
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
};

export default Settings;
