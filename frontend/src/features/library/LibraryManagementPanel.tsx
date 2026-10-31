import React, { useState, useEffect } from 'react';
import { apiFetch } from '../../api/client';
import { useSettings } from '../../contexts/SettingsContext';
import type { IndexStats } from '../../types/desk';
import '../../styles/library-management.css';

interface IndexProgress {
  processed_items?: number;
  total_items?: number;
  start_time?: number;
  elapsed_seconds?: number;
  eta_seconds?: number | null;
  skipped_items?: number;
  skip_reasons?: string[];
  mode?: 'incremental' | 'full';
  error?: string | null;  // Fatal error that stopped indexing
}

interface IndexStatus {
  status: string;
  progress?: IndexProgress;
}

const LibraryManagementPanel: React.FC = () => {
  const { settings, updateSettings } = useSettings();
  const [indexing, setIndexing] = useState(false);
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null);
  const [indexStats, setIndexStats] = useState<IndexStats | null>(null);
  const [embeddingModel, setEmbeddingModel] = useState(settings.embeddingModel || 'bge-base');
  const [savingModel, setSavingModel] = useState(false);
  const [modelSaveSuccess, setModelSaveSuccess] = useState(false);
  // Cloud embedding privacy gate: holds the model ID the user wants to switch to until
  // they explicitly acknowledge the privacy implications.
  const [cloudWarningTarget, setCloudWarningTarget] = useState<string | null>(null);
  
  // Exclusion picker state (collections, tags, item types)
  const [collections, setCollections] = useState<{ name: string; count?: number }[]>([]);
  const [tags, setTags] = useState<{ name: string; count?: number }[]>([]);
  const [itemTypes, setItemTypes] = useState<{ name: string; count?: number }[]>([]);
  const [exclCollections, setExclCollections] = useState<string[]>(settings.excludedCollections || []);
  const [exclTags, setExclTags] = useState<string[]>(settings.excludedTags || []);
  const [exclItemTypes, setExclItemTypes] = useState<string[]>(settings.excludedItemTypes || []);
  const [activeAxis, setActiveAxis] = useState<'collections' | 'tags' | 'itemTypes'>('collections');
  const [exclSearch, setExclSearch] = useState('');
  const [savingExclusions, setSavingExclusions] = useState(false);
  const [exclusionsSaved, setExclusionsSaved] = useState(false);
  const [exclusionMessage, setExclusionMessage] = useState<string | null>(null);
  const [exclusionError, setExclusionError] = useState<string | null>(null);

  const [statsError, setStatsError] = useState<string | null>(null);
  const [confirmingRebuild, setConfirmingRebuild] = useState(false);

  // Metadata sync state
  const [syncingMetadata, setSyncingMetadata] = useState(false);
  const [metadataSyncSuccess, setMetadataSyncSuccess] = useState<string | null>(null);
  const [metadataSyncError, setMetadataSyncError] = useState<string | null>(null);

  const indexingRef = React.useRef<boolean>(false);
  const pollRef = React.useRef<number | null>(null);

  // Sync embedding model if settings change externally
  useEffect(() => {
    setEmbeddingModel(settings.embeddingModel || 'bge-base');
  }, [settings.embeddingModel]);

  // Keep local exclusion selections in sync with saved settings
  // (by value: every settings save brings new arrays, which must not undo ticks not saved yet)
  const savedExclusions = JSON.stringify([settings.excludedCollections, settings.excludedTags, settings.excludedItemTypes]);
  useEffect(() => {
    const [saved, savedTags, savedTypes] = JSON.parse(savedExclusions);
    setExclCollections(saved || []);
    setExclTags(savedTags || []);
    setExclItemTypes(savedTypes || []);
  }, [savedExclusions]);

  // Load the library's collections, tags, and item types for the exclusion pickers
  useEffect(() => {
    (async () => {
      try {
        const [cRes, tRes, iRes] = await Promise.all([
          apiFetch('/api/library/collections').then(r => r.json()),
          apiFetch('/api/library/tags').then(r => r.json()),
          apiFetch('/api/library/item_types').then(r => r.json()),
        ]);
        setCollections(cRes.collections || []);
        setTags((tRes.tags || []).map((name: string) => ({ name })));
        setItemTypes(iRes.item_types || []);
      } catch (err) {
        console.error('Failed to fetch library metadata for exclusions', err);
      }
    })();
  }, []);

  const toggle = (list: string[], setList: (v: string[]) => void, name: string) =>
    setList(list.includes(name) ? list.filter(n => n !== name) : [...list, name]);

  const norm = (a?: string[]) => JSON.stringify([...(a || [])].sort());
  const exclusionsDirty =
    norm(exclCollections) !== norm(settings.excludedCollections) ||
    norm(exclTags) !== norm(settings.excludedTags) ||
    norm(exclItemTypes) !== norm(settings.excludedItemTypes);

  const handleSaveExclusions = async () => {
    setSavingExclusions(true);
    setExclusionMessage(null);
    setExclusionError(null);
    try {
      await updateSettings({
        excludedCollections: exclCollections,
        excludedTags: exclTags,
        excludedItemTypes: exclItemTypes,
      });
      // Apply immediately: remove matching items from the index so users don't
      // have to reindex. (Un-excluding still needs a Sync to re-embed items.)
      const resp = await apiFetch('/api/exclusions/purge', { method: 'POST' });
      const data = await resp.json();
      if (data?.purged_items > 0) {
        setExclusionMessage(`Removed ${data.purged_items} item${data.purged_items !== 1 ? 's' : ''} from the index.`);
      }
      await fetchStats();
      setExclusionsSaved(true);
      setTimeout(() => setExclusionsSaved(false), 3000);
    } catch (err) {
      setExclusionError(err instanceof Error ? err.message : 'The exclusions could not be saved.');
    } finally {
      setSavingExclusions(false);
    }
  };

  const handleClearExclusions = async () => {
    setExclCollections([]);
    setExclTags([]);
    setExclItemTypes([]);
    setExclusionMessage(null);
    setExclusionError(null);
    // Persist immediately so a following Sync actually restores excluded items.
    // (Clearing only removes the rules; run Sync to re-index what was removed.)
    setSavingExclusions(true);
    try {
      await updateSettings({ excludedCollections: [], excludedTags: [], excludedItemTypes: [] });
      setExclusionMessage('Exclusions cleared. Sync to bring back any removed items.');
      await fetchStats();
    } catch (err) {
      setExclusionError(err instanceof Error ? err.message : 'The exclusions could not be cleared.');
    } finally {
      setSavingExclusions(false);
    }
  };

  const hasSelections =
    exclCollections.length > 0 || exclTags.length > 0 || exclItemTypes.length > 0;

  const exclusionAxes = [
    { key: 'collections' as const, label: 'Collections', options: collections, selected: exclCollections, setSelected: setExclCollections },
    { key: 'tags' as const, label: 'Tags', options: tags, selected: exclTags, setSelected: setExclTags },
    { key: 'itemTypes' as const, label: 'Item type', options: itemTypes, selected: exclItemTypes, setSelected: setExclItemTypes },
  ];
  const activeAxisData = exclusionAxes.find(a => a.key === activeAxis)!;
  const filteredOptions = activeAxisData.options.filter(o =>
    o.name.toLowerCase().includes(exclSearch.trim().toLowerCase())
  );

  const handleEmbeddingModelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    if (value.includes(':')) {
      // Cloud model selected — show privacy warning before applying the change
      setCloudWarningTarget(value);
    } else {
      setEmbeddingModel(value);
    }
  };

  const handleSaveModel = async () => {
    setSavingModel(true);
    try {
      await updateSettings({ embeddingModel });
      setModelSaveSuccess(true);
      setTimeout(() => setModelSaveSuccess(false), 3000);
    } catch {
      // the error banner shows it, including the refusal while indexing runs
    } finally {
      setSavingModel(false);
    }
  };

  // Fetch index stats
  const fetchStats = async () => {
    try {
      const resp = await apiFetch('/api/index_stats');
      const data = await resp.json();
      setIndexStats(data);
      setStatsError(null);
    } catch (err) {
      setStatsError(err instanceof Error ? err.message : 'The index could not be read.');
    }
  };

  useEffect(() => {
    fetchStats();
    // This panel unmounts when you leave it; a job started earlier is still running.
    apiFetch('/api/index_status')
      .then(r => r.json())
      .then((js: IndexStatus) => {
        setIndexStatus(js);
        if (js.status === 'indexing') {
          indexingRef.current = true;
          setIndexing(true);
          followIndexing();
        }
      })
      .catch(() => undefined); // fetchStats above reports an unreachable backend
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  /** Poll until the running job ends, then refresh the numbers. */
  const followIndexing = () => {
    const finish = () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
      setIndexing(false);
      indexingRef.current = false;
    };
    const poll = async () => {
      try {
        const js: IndexStatus = await (await apiFetch('/api/index_status')).json();
        setIndexStatus(js);
        if (js.status === 'indexing') return;
        await fetchStats();
      } catch (err) {
        console.error('Failed to fetch index_status', err); // one miss must not abandon a running job
        return;
      }
      finish();
    };
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(poll, 1500);
    poll();
  };

  const startIndexing = async (incremental: boolean) => {
    if (indexing || indexingRef.current) return;

    indexingRef.current = true;
    setIndexing(true);
    setConfirmingRebuild(false);

    try {
      await apiFetch("/api/index_library", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ incremental })
      });
      followIndexing();
    } catch (e) {
      setIndexing(false);
      indexingRef.current = false;
      setIndexStatus({ status: 'error', progress: { error: e instanceof Error ? e.message : 'The sync could not start.' } });
    }
  };

  const stopIndexing = async () => {
    try {
      await apiFetch('/api/index_cancel', { method: 'POST' });
    } catch (e) {
      console.error('Stop request failed', e);
    }
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setIndexing(false);
    indexingRef.current = false;
    setIndexStatus({ status: 'idle', progress: undefined });
    await fetchStats();
  };

  const handleMetadataSync = async () => {
    setMetadataSyncSuccess(null);
    setMetadataSyncError(null);
    setSyncingMetadata(true);

    try {
      const response = await apiFetch('/api/metadata/sync', {
        method: 'POST',
      });
      const result = await response.json();

      if (result.status === 'completed') {
        setMetadataSyncSuccess(`Updated the details of ${result.summary?.unique_items || 0} items.`);
        // Refresh stats after syncing
        await fetchStats();
      } else {
        setMetadataSyncError('The details could not be updated.');
      }
    } catch (err) {
      setMetadataSyncError(err instanceof Error ? err.message : 'The details could not be updated.');
    } finally {
      setSyncingMetadata(false);
    }
  };

  const progress = indexStatus?.status === 'indexing' ? indexStatus.progress : undefined;

  return (
    <div className="side-panel">
      <div className="panel-head">
        <h2 className="panel-head__title">Library</h2>
        <span className="panel-head__hint">index and exclusions</span>
      </div>

      <div className="lib-panel">

        <section className="lib-section">
          {indexStats?.zotero_error && (
            <p className="desk-notice desk-notice--error">
              Zotero's database could not be read at {indexStats.zotero_path} ({indexStats.zotero_error}). If Zotero is
              open, close it; otherwise check the path in Settings.
            </p>
          )}
          {statsError ? (
            <p className="desk-notice desk-notice--error">{statsError}</p>
          ) : indexStats ? (
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-value">{indexStats.indexed_items.toLocaleString()}</div>
                <div className="stat-label">Items indexed</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{indexStats.total_chunks.toLocaleString()}</div>
                <div className="stat-label">Passages</div>
              </div>
              <div className="stat-card">
                <div className="stat-value stat-value-highlight">{indexStats.new_items.toLocaleString()}</div>
                <div className="stat-label">New in Zotero</div>
              </div>
            </div>
          ) : (
            <div className="loading-stats">Reading the index…</div>
          )}

          <div className="lib-action-row">
            <button className="btn btn--primary" onClick={() => startIndexing(true)} disabled={indexing}>
              {indexing
                ? (progress?.mode === 'full' ? 'Rebuilding…' : 'Syncing…')
                : indexStats?.new_items
                  ? `Sync ${indexStats.new_items.toLocaleString()} new item${indexStats.new_items !== 1 ? 's' : ''}`
                  : 'Sync library'}
            </button>
            {indexing && (
              <button className="lib-cancel-btn" onClick={stopIndexing}>
                {progress?.mode === 'full' ? 'Stop' : 'Pause'}
              </button>
            )}
          </div>

          {progress && !progress.error && (
            <div className="indexing-progress">
              <div className="progress-header">
                <span className="progress-label">{progress.mode === 'full' ? 'Rebuilding' : 'Syncing'}…</span>
                {progress.eta_seconds != null && progress.eta_seconds > 0 && (
                  <span className="progress-eta">
                    ~{progress.eta_seconds < 60 ? `${progress.eta_seconds}s` : `${Math.ceil(progress.eta_seconds / 60)}m`}
                  </span>
                )}
              </div>

              <div className="progress-bar">
                {progress.total_items ? (
                  <div
                    className="progress-fill"
                    style={{ width: `${Math.min(100, Math.round((100 * (progress.processed_items ?? 0)) / progress.total_items))}%` }}
                  />
                ) : (
                  <div className="progress-fill-indeterminate" />
                )}
              </div>

              <div className="progress-details">
                {progress.processed_items ?? 0} / {progress.total_items ?? 0} items
                {progress.mode === 'incremental' && (progress.skipped_items ?? 0) > 0 && (
                  <span> ({progress.skipped_items} already indexed)</span>
                )}
              </div>
            </div>
          )}

          {indexStatus?.progress?.error && (
            <p className="desk-notice desk-notice--error">{indexStatus.progress.error}</p>
          )}

          <p className="lib-hint">
            Indexes new items only. It is safe to stop or close the app: the next sync picks up where this one left off.
          </p>
        </section>

        <section className="lib-section">
          <h3 className="scope-section-title">Excluded from indexing</h3>

          <p className="lib-hint">
            Items in an excluded collection, tag or type are skipped, and removed from the index when you save.
          </p>

          <div className="toggle-group toggle-group--three" role="group" aria-label="Exclude by">
            {exclusionAxes.map(axis => (
              <button
                key={axis.key}
                type="button"
                className={`toggle-btn ${activeAxis === axis.key ? 'active' : ''}`}
                aria-pressed={activeAxis === axis.key}
                onClick={() => { setActiveAxis(axis.key); setExclSearch(''); }}
              >
                {axis.label}
                {axis.selected.length > 0 && <span className="toggle-btn__count"> {axis.selected.length}</span>}
              </button>
            ))}
          </div>

          <input
            type="text"
            className="lib-filter"
            value={exclSearch}
            onChange={e => setExclSearch(e.target.value)}
            placeholder={`Search ${activeAxisData.label.toLowerCase()}…`}
            aria-label={`Search ${activeAxisData.label.toLowerCase()}`}
          />

          {activeAxisData.options.length === 0 ? (
            <p className="lib-hint">None found in your library.</p>
          ) : filteredOptions.length === 0 ? (
            <p className="lib-hint">No matches for “{exclSearch}”.</p>
          ) : (
            <div className="lib-checklist">
              {filteredOptions.map(o => (
                <label key={o.name}>
                  <input
                    type="checkbox"
                    checked={activeAxisData.selected.includes(o.name)}
                    onChange={() => toggle(activeAxisData.selected, activeAxisData.setSelected, o.name)}
                  />
                  <span>{o.name}</span>
                  {o.count != null && <span className="lib-checklist__count">{o.count}</span>}
                </label>
              ))}
            </div>
          )}

          <p className="lib-hint">
            {exclusionAxes.every(a => a.selected.length === 0) ? (
              'Nothing excluded: your whole library will be indexed.'
            ) : (
              <>
                <strong>Excluding:</strong>{' '}
                {exclusionAxes
                  .filter(a => a.selected.length > 0)
                  .map(a => `${a.label} (${a.selected.length}): ${a.selected.join(', ')}`)
                  .join('  ·  ')}
              </>
            )}
          </p>

          <div className="lib-action-row">
            <button className="btn btn--primary" onClick={handleSaveExclusions} disabled={savingExclusions || !exclusionsDirty}>
              {savingExclusions ? 'Saving…' : exclusionsSaved ? 'Saved' : 'Save exclusions'}
            </button>
            <button className="btn" onClick={handleClearExclusions} disabled={savingExclusions || !hasSelections}>
              Clear
            </button>
          </div>

          {exclusionMessage && <p className="desk-notice">{exclusionMessage}</p>}
          {exclusionError && <p className="desk-notice desk-notice--error">{exclusionError}</p>}
        </section>

        <details className="lib-section lib-section-last lib-advanced">
          <summary>Advanced</summary>

          <h3 className="scope-section-title">Update item details</h3>
          <p className="lib-hint">
            Picks up titles, authors, tags and collections you changed in Zotero, without reading the PDFs again.
          </p>
          <button className="btn" onClick={handleMetadataSync} disabled={syncingMetadata}>
            {syncingMetadata ? 'Updating…' : 'Update details from Zotero'}
          </button>
          {metadataSyncSuccess && <p className="desk-notice">{metadataSyncSuccess}</p>}
          {metadataSyncError && <p className="desk-notice desk-notice--error">{metadataSyncError}</p>}

          <h3 className="scope-section-title">Embedding model</h3>
          <p className="lib-hint">
            Turns passages into something searchable by meaning. {indexStats ? `In use: ${indexStats.current_embedding_model}. ` : ''}
            Changing it means rebuilding the index. To compare models, create a new profile instead.
          </p>
          <select className="lib-select" aria-label="Embedding model" value={embeddingModel} onChange={handleEmbeddingModelChange}>
            <optgroup label="Local (runs on this device)">
              <option value="bge-base">BAAI/bge-base-en-v1.5: best quality, slower</option>
              <option value="specter">SPECTER: made for scientific papers</option>
              <option value="minilm-l6">all-MiniLM-L6-v2: good quality, faster</option>
              <option value="minilm-l3">paraphrase-MiniLM-L3-v2: fastest</option>
            </optgroup>
            <optgroup label="Multilingual (local, runs on this device)">
              <option value="bge-m3">BAAI/bge-m3: 100+ languages incl. Chinese, ~2.3GB download</option>
              <option value="bge-large-zh">BAAI/bge-large-zh-v1.5: Chinese, ~1.3GB download</option>
              <option value="multilingual-minilm">paraphrase-multilingual-MiniLM-L12-v2: 50+ languages, ~470MB download</option>
            </optgroup>
            <optgroup label="Cloud (text is sent to an external API)">
              <option value="openai:text-embedding-3-small">OpenAI text-embedding-3-small: fast</option>
              <option value="openai:text-embedding-3-large">OpenAI text-embedding-3-large: highest quality</option>
            </optgroup>
          </select>
          <div className="lib-action-row">
            <button className="btn" onClick={handleSaveModel} disabled={savingModel || embeddingModel === settings.embeddingModel}>
              {savingModel ? 'Saving…' : modelSaveSuccess ? 'Saved' : 'Save model'}
            </button>
          </div>

          <h3 className="scope-section-title">Rebuild the index</h3>
          <p className="lib-hint">
            Reads every PDF again and replaces its passages, which can take hours. Only needed if the index is damaged or you changed how PDFs are read.
          </p>
          {confirmingRebuild ? (
            <div className="lib-action-row">
              <button className="btn btn--danger" onClick={() => startIndexing(false)} disabled={indexing}>
                Yes, rebuild
              </button>
              <button className="btn" onClick={() => setConfirmingRebuild(false)}>Keep the index</button>
            </div>
          ) : (
            <button className="btn" onClick={() => setConfirmingRebuild(true)} disabled={indexing}>Rebuild the index…</button>
          )}
        </details>

      </div>

      {/* Cloud embedding privacy warning modal */}
      {cloudWarningTarget && (
        <div
          className="cloud-warning-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="cloud-warning-title"
          onKeyDown={e => { if (e.key === 'Escape') setCloudWarningTarget(null); }}
        >
          <div className="cloud-warning-modal">
            <div className="cloud-warning-header">
              <span className="cloud-warning-icon" aria-hidden="true">⚠️</span>
              <h3 id="cloud-warning-title">Your document text will leave this device</h3>
            </div>

            <div className="cloud-warning-body">
              <span className="cloud-warning-model-label">{cloudWarningTarget}</span>
              <p>
                Cloud embedding models send text to an external API. If you proceed:
              </p>
              <ul>
                <li>
                  The full text of every PDF in your library will be sent to{' '}
                  <strong>OpenAI's servers</strong> to generate embeddings.
                </li>
                <li>
                  This happens <strong>every time you index</strong> and every time you
                  send a chat message (your query is also embedded via the API).
                </li>
                <li>
                  Your <strong>OpenAI API key</strong> must remain configured for the
                  app to function — it is not a one-time operation.
                </li>
                <li>
                  Data is subject to{' '}
                  <strong>OpenAI's privacy and data retention policies</strong>.
                </li>
              </ul>
              <p style={{ marginTop: '10px' }}>
                If privacy is a concern, use a local model instead.
              </p>
            </div>

            <div className="cloud-warning-footer">
              <button
                className="btn"
                autoFocus
                onClick={() => setCloudWarningTarget(null)}
              >
                Cancel
              </button>
              <button
                className="btn btn--danger"
                onClick={() => {
                  setEmbeddingModel(cloudWarningTarget);
                  setCloudWarningTarget(null);
                }}
              >
                I understand — use cloud embeddings
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LibraryManagementPanel;
