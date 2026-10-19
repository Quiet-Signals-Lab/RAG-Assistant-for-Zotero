import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSettings, ModelInfo, ProviderInfo } from '../contexts/SettingsContext';
import { apiFetch } from '../api/client';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import ProfileSelector from '../components/profile/ProfileSelector';
import { useAppUpdater } from '../hooks/useAppUpdater';
import { isElectron } from '../utils/electron';
import RoomHeader from '../components/layout/RoomHeader';
import '../styles/settings.css';

const Settings: React.FC = () => {
  const navigate = useNavigate();
  const { settings, updateSettings, loading, availableProviders } = useSettings();
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
  const [activeTab, setActiveTab] = useState<TabId>('general');
  
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
      // A local server that is not running is a normal state for an optional provider.
      console.warn(`${providerId} is not reachable; its models will load once it is running.`, err);
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

  // One provider: a ledger row with its switch, then its credentials when enabled.
  const renderProviderCard = (provider: ProviderInfo) => {
    const config = formData.providers[provider.id];
    const validation = providerValidation[provider.id];
    const isValidating = validatingProvider === provider.id;
    const envKey = detectedEnvKeys[provider.id];

    return (
      <div key={provider.id} className="provider-config-card">
        <div className="provider-header">
          <label className="provider-toggle">
            <input
              type="checkbox"
              checked={config?.enabled || false}
              onChange={(e) => handleProviderEnabledChange(provider.id, e.target.checked)}
            />
            <span className="provider-name">{provider.label}</span>
          </label>
          {validation && (
            <span className={`provider-status ${validation.valid ? 'valid' : 'invalid'}`} role="status">
              {validation.valid ? 'Connected' : validation.message}
            </span>
          )}
        </div>

        {config?.enabled && (
          <div className="provider-credentials">
            {provider.requires_api_key && (
              <div className="settings-field">
                <label className="settings-label" htmlFor={`${provider.id}-api-key`}>
                  {provider.id === 'github_models' ? 'GitHub token' : 'API key'}
                  {provider.id === 'google' && <span className="settings-label__note">unreliable</span>}
                  {envKey?.detected && (
                    <span className="settings-label__note" title={`Using ${envKey.env_var} from the environment`}>
                      from {envKey.env_var ?? 'the environment'}
                    </span>
                  )}
                </label>
                <div className="settings-input-group">
                  <Input
                    id={`${provider.id}-api-key`}
                    type={showApiKeys[provider.id] ? 'text' : 'password'}
                    value={config.credentials.api_key || ''}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      handleProviderCredentialChange(provider.id, 'api_key', e.target.value)
                    }
                    placeholder={provider.id === 'github_models' ? 'GitHub personal access token' : 'API key'}
                    className="settings-input"
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKeys(prev => ({ ...prev, [provider.id]: !prev[provider.id] }))}
                    className="api-key-toggle"
                    aria-pressed={!!showApiKeys[provider.id]}
                  >
                    {showApiKeys[provider.id] ? 'Hide' : 'Show'}
                  </button>
                </div>
                {['openai', 'mistral', 'groq', 'openrouter', 'github_models'].includes(provider.id) && (
                  <p className="settings-hint">
                    {provider.id === 'github_models'
                      ? 'Generate a token at github.com/settings/tokens; no scopes are needed. Works with GitHub Copilot subscriptions.'
                      : 'Models are found from your key when you test the connection.'}
                  </p>
                )}
              </div>
            )}

            {['openai', 'mistral', 'groq', 'openrouter'].includes(provider.id) && (
              <div className="settings-field">
                <label className="settings-label" htmlFor={`${provider.id}-base-url`}>
                  Custom endpoint <span className="settings-label__note">optional</span>
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
                <p className="settings-hint">
                  Leave blank for the default. Useful for Azure OpenAI, proxies or your own deployment.
                </p>
              </div>
            )}

            {(provider.id === 'ollama' || provider.id === 'lmstudio') && (
              <div className="settings-field">
                <label className="settings-label" htmlFor={`${provider.id}-base-url`}>Base URL</label>
                <Input
                  id={`${provider.id}-base-url`}
                  type="text"
                  value={config.credentials.base_url || (provider.id === 'ollama' ? 'http://localhost:11434' : 'http://localhost:1234')}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    handleProviderCredentialChange(provider.id, 'base_url', e.target.value)
                  }
                  className="settings-input"
                />
                {provider.id === 'lmstudio' && (
                  <p className="settings-hint">LM Studio must be running with its local server started.</p>
                )}
              </div>
            )}

            <Button onClick={() => handleSaveAndTest(provider.id)} variant="secondary" disabled={isValidating || saving}>
              {isValidating ? 'Testing…' : saving ? 'Saving…' : 'Save and test'}
            </Button>
          </div>
        )}
      </div>
    );
  };

  const localProviders = availableProviders.filter(p => !p.requires_api_key);
  const cloudProviders = availableProviders.filter(p => p.requires_api_key);
  const backLabel = settings.interfaceMode === 'chat' ? 'Back to the chat' : 'Back to search';

  if (loading) {
    return (
      <div className="settings-page">
        <RoomHeader title="Settings" />
        <p className="settings-loading">Loading settings…</p>
      </div>
    );
  }

  return (
    <div className="settings-page">
      <RoomHeader title="Settings">
        <div className="room-header__fill" />
        <button type="button" className="btn" onClick={() => navigate('/')}>← {backLabel}</button>
      </RoomHeader>

      <div className="settings-body">
        <nav className="settings-nav" aria-label="Settings sections">
          {TABS.map(tab => (
            <button
              key={tab.id}
              type="button"
              className="settings-tab"
              aria-current={activeTab === tab.id ? 'page' : undefined}
              onClick={() => setActiveTab(tab.id)}
            >
              <span className="settings-tab__label">{tab.label}</span>
              <span className="settings-tab__note">{tab.note}</span>
            </button>
          ))}
        </nav>

        <main className="settings-main">
          <div className="panel-head">
            <h1 className="panel-head__title">{TABS.find(t => t.id === activeTab)?.label}</h1>
          </div>

          {activeTab === 'general' && (
            <>
              <Section title="Interface" description="How you work with your library.">
                <fieldset className="settings-choices">
                  <legend className="sr-only">Interface</legend>
                  <label className="settings-check">
                    <input
                      type="radio"
                      name="interfaceMode"
                      value="desk"
                      checked={settings.interfaceMode !== 'chat'}
                      onChange={() => updateSettings({ interfaceMode: 'desk' })}
                    />
                    <span>
                      <span className="settings-check__label">Search</span>
                      <span className="settings-hint">
                        Search your library and get back a ranked bibliography with the evidence open at the page.
                        No answers are written, and no model is needed.
                      </span>
                    </span>
                  </label>
                  <label className="settings-check">
                    <input
                      type="radio"
                      name="interfaceMode"
                      value="chat"
                      checked={settings.interfaceMode === 'chat'}
                      onChange={() => updateSettings({ interfaceMode: 'chat' })}
                    />
                    <span>
                      <span className="settings-check__label">Chat</span>
                      <span className="settings-hint">
                        A model answers your questions from passages in your library, citing each one.
                        It needs a configured model. From search, “Chat about these” opens it on the items you found.
                      </span>
                    </span>
                  </label>
                </fieldset>
              </Section>

              <Section title="Appearance" description="Changes apply at once.">
                <label className="settings-check">
                  <input
                    type="checkbox"
                    checked={settings.theme === 'dark'}
                    onChange={(e) => updateSettings({ theme: e.target.checked ? 'dark' : 'light' })}
                  />
                  <span>
                    <span className="settings-check__label">Dark theme</span>
                    <span className="settings-hint">Light text on a dark background.</span>
                  </span>
                </label>
              </Section>

              <Section title="Zotero" description="Where your library lives on this computer. It is only ever read.">
                <div className="settings-field">
                  <label className="settings-label" htmlFor="zotero-path">Zotero database</label>
                  <input
                    id="zotero-path"
                    type="text"
                    className="settings-input"
                    value={formData.zoteroPath}
                    onChange={(e) => handleInputChange('zoteroPath', e.target.value)}
                    placeholder={navigator.platform.startsWith('Win') ? 'C:\\Users\\YourName\\Zotero\\zotero.sqlite' : (navigator.platform.startsWith('Mac') ? '/Users/YourName/Zotero/zotero.sqlite' : '~/Zotero/zotero.sqlite')}
                    spellCheck={false}
                  />
                  <p className="settings-hint">The full path to <code>zotero.sqlite</code>, in your Zotero data folder.</p>
                </div>
                <div className="settings-field">
                  <label className="settings-label" htmlFor="pdf-path">
                    PDF storage folder <span className="settings-label__note">optional</span>
                  </label>
                  <input
                    id="pdf-path"
                    type="text"
                    className="settings-input"
                    value={formData.pdfStoragePath ?? ''}
                    onChange={(e) => handleInputChange('pdfStoragePath', e.target.value)}
                    placeholder={navigator.platform.startsWith('Win') ? 'C:\\Users\\YourName\\Zotero\\storage' : (navigator.platform.startsWith('Mac') ? '/Users/YourName/Zotero/storage' : '~/Zotero/storage')}
                    spellCheck={false}
                  />
                  <p className="settings-hint">Leave blank to use the storage folder next to the database.</p>
                </div>
              </Section>

              <Section title="Profile" description="Each profile keeps its own settings, history and index.">
                <ProfileSelector />
              </Section>

              {isElectron() && (
                <Section title="Updates" description="Updates are never installed automatically.">
                  <dl className="settings-ledger">
                    <div><dt>Installed</dt><dd className="mono">{updater.currentVersion || '…'}</dd></div>
                    <div>
                      <dt>Status</dt>
                      <dd role="status">
                        {updater.status === 'idle' && 'Not checked yet'}
                        {updater.status === 'checking' && 'Checking…'}
                        {updater.status === 'not-available' && 'Up to date'}
                        {updater.status === 'available' && updater.updateInfo && `Version ${updater.updateInfo.version} is available`}
                        {updater.status === 'downloading' && updater.downloadProgress &&
                          `Downloading, ${updater.downloadProgress.percent.toFixed(0)}% (${(updater.downloadProgress.transferred / 1024 / 1024).toFixed(1)} of ${(updater.downloadProgress.total / 1024 / 1024).toFixed(1)} MB)`}
                        {updater.status === 'downloaded' && updater.updateInfo && `Version ${updater.updateInfo.version} is ready; the app restarts to install it`}
                        {updater.status === 'error' && <span className="settings-error">{updater.error}</span>}
                      </dd>
                    </div>
                  </dl>
                  {updater.status === 'available' && updater.updateInfo?.releaseNotes && (
                    <details className="release-notes">
                      <summary>Release notes</summary>
                      <div className="release-notes-content">{updater.updateInfo.releaseNotes}</div>
                    </details>
                  )}
                  <div className="settings-buttons">
                    {(updater.status === 'idle' || updater.status === 'not-available' || updater.status === 'error') && (
                      <Button onClick={updater.checkForUpdates} variant="secondary">Check for updates</Button>
                    )}
                    {updater.status === 'available' && (
                      <Button
                        onClick={() => window.electron?.openExternal('https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases/latest')}
                        variant="primary"
                      >
                        Download from GitHub Releases
                      </Button>
                    )}
                  </div>
                  <p className="settings-note">
                    New versions are downloaded and installed by hand from{' '}
                    <a href="https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/releases" target="_blank" rel="noopener noreferrer">GitHub Releases</a>.
                    Profiles, keys, indexes and settings carry over.
                  </p>
                </Section>
              )}

              <Section title="Notifications" description="Chat only: when the model has finished an answer.">
                <label className="settings-check">
                  <input
                    type="checkbox"
                    checked={formData.showSystemNotification ?? true}
                    onChange={(e) => handleBooleanChange('showSystemNotification', e.target.checked)}
                  />
                  <span>
                    <span className="settings-check__label">System notification</span>
                    <span className="settings-hint">A desktop notification when an answer is ready.</span>
                  </span>
                </label>
                <label className="settings-check">
                  <input
                    type="checkbox"
                    checked={formData.playSoundNotification ?? false}
                    onChange={(e) => handleBooleanChange('playSoundNotification', e.target.checked)}
                  />
                  <span>
                    <span className="settings-check__label">Sound</span>
                    <span className="settings-hint">A short sound when an answer is ready.</span>
                  </span>
                </label>
              </Section>

              <Section title="Support" description="Free and open source, made by Quiet Signals Lab.">
                <div className="settings-buttons">
                  <Button
                    onClick={() => window.open('https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero/issues/new', '_blank', 'noopener,noreferrer')}
                    variant="secondary"
                  >
                    Report a bug
                  </Button>
                  <Button
                    onClick={() => window.open('https://github.com/sponsors/aahepburn', '_blank', 'noopener,noreferrer')}
                    variant="secondary"
                  >
                    Sponsor the project
                  </Button>
                </div>
                <p className="settings-hint">
                  A good bug report has a screenshot, the error message, and the console log: open the developer tools
                  with <kbd>Cmd</kbd> <kbd>Option</kbd> <kbd>I</kbd> on a Mac or <kbd>Ctrl</kbd> <kbd>Shift</kbd> <kbd>I</kbd> elsewhere,
                  then copy from the Console tab.
                </p>
                <p className="settings-hint settings-licence">
                  © 2025–2026 Alexander Hepburn · Licensed under the{' '}
                  <a href="https://www.gnu.org/licenses/gpl-3.0.html" target="_blank" rel="noopener noreferrer">GNU General Public License v3.0</a>
                </p>
              </Section>
            </>
          )}

          {activeTab === 'local' && (
            <Section
              title="Local providers"
              description="Model servers on this computer. No key is needed and nothing leaves the machine. Used by the language model jobs (optional) and by chat."
            >
              {localProviders.map(provider => renderProviderCard(provider))}
            </Section>
          )}

          {activeTab === 'cloud' && (
            <Section
              title="Cloud providers"
              description="External model services. They need an API key, and your query and passages are sent to them. Used by the language model jobs (optional) and by chat."
            >
              {cloudProviders.map(provider => renderProviderCard(provider))}
            </Section>
          )}

          {activeTab === 'advanced' && (
            <Section
              title="Evidence per answer"
              description="Chat only. Search always retrieves the same depth, whatever the model."
            >
              <div className="settings-field">
                <label className="settings-label" htmlFor="max-sources">Passages per question</label>
                <select
                  id="max-sources"
                  className="settings-input"
                  value={formData.maxSources ?? 0}
                  onChange={e => {
                    const v = parseInt(e.target.value, 10);
                    setFormData(prev => ({ ...prev, maxSources: v }));
                    setSaveSuccess(false);
                    setSaveError(null);
                  }}
                >
                  <option value={0}>Automatic, from the model's context window (recommended)</option>
                  {[4, 6, 8, 10, 12, 16, 20, 30].map(n => <option key={n} value={n}>{n} passages</option>)}
                </select>
                <p className="settings-hint">
                  Several passages can come from one paper, so fewer sources are cited than passages sent. Raise this
                  if answers miss sources you know are there. Local models default to 6; more can overflow models with
                  a context window under 16k tokens.
                </p>
              </div>
            </Section>
          )}
        </main>
      </div>

      <footer className="settings-savebar">
        <div className="settings-savebar__status" role="status" aria-live="polite">
          {saveSuccess && <span className="settings-success">Saved</span>}
          {saveError && <span className="settings-error">{saveError}</span>}
        </div>
        <Button onClick={() => navigate('/')} variant="secondary">Cancel</Button>
        <Button onClick={handleSave} disabled={saving} variant="primary">{saving ? 'Saving…' : 'Save settings'}</Button>
      </footer>
    </div>
  );
};

type TabId = 'general' | 'local' | 'cloud' | 'advanced';

const TABS: { id: TabId; label: string; note: string }[] = [
  { id: 'general', label: 'General', note: 'interface, Zotero, profile' },
  { id: 'local', label: 'Local models', note: 'Ollama, LM Studio' },
  { id: 'cloud', label: 'Cloud providers', note: 'API keys' },
  { id: 'advanced', label: 'Chat retrieval', note: 'chat' },
];

/** A ledger row: what the setting is on the left, the controls on the right. */
const Section: React.FC<React.PropsWithChildren<{ title: string; description?: string }>> = ({ title, description, children }) => (
  <section className="settings-section">
    <div className="settings-section__intro">
      <h2 className="settings-section-title">{title}</h2>
      {description && <p className="settings-section-description">{description}</p>}
    </div>
    <div className="settings-section__body">{children}</div>
  </section>
);

export default Settings;
