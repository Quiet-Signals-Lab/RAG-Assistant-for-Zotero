import React, { useState, useEffect } from 'react';
import { useSettings, ModelInfo } from '../../contexts/SettingsContext';
import { apiFetch } from '../../api/client';
import '../../styles/active-model-panel.css';

/**
 * ActiveModelPanel displays the active provider and model selection
 * in the left sidebar for quick model switching during chat sessions.
 */
const ActiveModelPanel: React.FC = () => {
  const { settings, updateSettings, availableProviders } = useSettings();
  const [availableModels, setAvailableModels] = useState<Record<string, ModelInfo[]>>({});
  const [loadingModels, setLoadingModels] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

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

  // Load models for enabled providers on mount; retry if list is empty (e.g. local server wasn't ready)
  useEffect(() => {
    Object.entries(settings.providers).forEach(([providerId, config]) => {
      const models = availableModels[providerId];
      if (config.enabled && !loadingModels[providerId] && (!models || models.length === 0)) {
        loadModelsForProvider(providerId);
      }
    });
  }, [settings.providers]);

  // Auto-select first model when models load for active provider if no model is currently selected
  useEffect(() => {
    const models = availableModels[settings.activeProviderId];
    if (models && models.length > 0 && !settings.activeModel) {
      handleModelChange(models[0].id);
    }
  }, [availableModels[settings.activeProviderId]]);

  // Auto-switch active provider if the current one is disabled or has no credentials
  useEffect(() => {
    const activeIsConfigured = configuredProviders.find(p => p.id === settings.activeProviderId);
    if (!activeIsConfigured && configuredProviders.length > 0 && !saving) {
      handleProviderChange(configuredProviders[0].id);
    }
  }, [settings.activeProviderId, settings.providers, availableProviders]);

  const handleProviderChange = async (providerId: string) => {
    try {
      setSaving(true);
      await updateSettings({ activeProviderId: providerId, activeModel: '' });
      
      // Always reload models when switching providers to ensure fresh data
      await loadModelsForProvider(providerId);
      
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (err) {
      console.error('Failed to update provider:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleModelChange = async (modelId: string) => {
    try {
      setSaving(true);
      await updateSettings({ activeModel: modelId });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (err) {
      console.error('Failed to update model:', err);
    } finally {
      setSaving(false);
    }
  };

  const currentProvider = availableProviders.find(p => p.id === settings.activeProviderId);
  const models = availableModels[settings.activeProviderId] || [];

  // Filter providers to only show those with credentials or local providers
  const configuredProviders = availableProviders.filter(provider => {
    const providerConfig = settings.providers[provider.id];
    
    // Skip if not enabled
    if (!providerConfig?.enabled) {
      return false;
    }
    
    // Local providers (no API key required) - always show if enabled
    if (provider.id === 'ollama' || provider.id === 'lmstudio') {
      return true;
    }
    
    // Cloud providers - only show if API key is configured
    if (provider.requires_api_key) {
      const apiKey = providerConfig?.credentials?.api_key;
      return apiKey && apiKey.length > 0;
    }
    
    return true;
  });

  return (
    <>
      <header className="active-model-header">
        <div>
          <div className="active-model-title">Active Model</div>
          <div className="active-model-subtitle">Provider and model for chat</div>
        </div>
      </header>
      
      <main className="active-model-panel">
        <div className="active-model-note">
          <strong>Note:</strong> Only providers with API keys configured or local servers running are shown.
        </div>

        <div className="active-model-field">
          <label className="active-model-label" htmlFor="active-provider">
            Provider
          </label>
          <select
            id="active-provider"
            value={settings.activeProviderId}
            onChange={(e) => handleProviderChange(e.target.value)}
            className="active-model-select"
            disabled={saving}
          >
            {configuredProviders.length > 0 ? (
              configuredProviders.map(provider => (
                <option key={provider.id} value={provider.id}>
                  {provider.label}
                </option>
              ))
            ) : (
              <option value="">No providers configured</option>
            )}
          </select>
          {configuredProviders.length === 0 && (
            <p className="active-model-hint" style={{ color: 'var(--text-warning, #ff9800)' }}>
              Configure API keys in Settings to use cloud providers, or enable Ollama/LM Studio for local models.
            </p>
          )}
        </div>

        <div className="active-model-field">
          <label className="active-model-label" htmlFor="active-model">
            Model
            {loadingModels[settings.activeProviderId] ? (
              <span className="active-model-loading"> (loading...)</span>
            ) : (
              <button
                className="active-model-refresh-btn"
                onClick={() => loadModelsForProvider(settings.activeProviderId)}
                title="Refresh model list"
                aria-label="Refresh model list"
              >
                &#x21bb;
              </button>
            )}
          </label>
          <select
            id="active-model"
            value={settings.activeModel}
            onChange={(e) => handleModelChange(e.target.value)}
            className="active-model-select"
            disabled={loadingModels[settings.activeProviderId] || saving}
          >
            {models.length > 0 ? (
              models.map(model => (
                <option key={model.id} value={model.id}>
                  {model.id}{model.description && ` - ${model.description}`}
                </option>
              ))
            ) : (
              <option value="">No models available</option>
            )}
          </select>
          <p className="active-model-hint">
            Make sure your provider is running and has models loaded.
          </p>
        </div>

        {currentProvider && (
          <div className="active-model-info">
            <div className="active-model-info-row">
              <span className="active-model-info-label">Streaming:</span>
              <span className="active-model-info-value">
                {currentProvider.supports_streaming ? 'Enabled' : 'Disabled'}
              </span>
            </div>
            {settings.activeModel && (
              <div className="active-model-info-row">
                <span className="active-model-info-label">Selected:</span>
                <span className="active-model-info-value">{settings.activeModel}</span>
              </div>
            )}
          </div>
        )}

        {/* Fixed space for save notification */}
        <div className="active-model-notification-container">
          {saveSuccess && (
            <div className="active-model-success">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Saved
            </div>
          )}
        </div>
      </main>
    </>
  );
};

export default ActiveModelPanel;
