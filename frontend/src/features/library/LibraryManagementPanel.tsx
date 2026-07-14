import React, { useState, useEffect } from 'react';
import { apiFetch } from '../../api/client';
import { useSettings } from '../../contexts/SettingsContext';
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

interface IndexStats {
  indexed_items: number;
  total_chunks: number;
  zotero_items: number;
  new_items: number;
  current_embedding_model: string;
  collection_name: string;
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
  useEffect(() => {
    setExclCollections(settings.excludedCollections || []);
    setExclTags(settings.excludedTags || []);
    setExclItemTypes(settings.excludedItemTypes || []);
  }, [settings.excludedCollections, settings.excludedTags, settings.excludedItemTypes]);

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
    try {
      await updateSettings({
        excludedCollections: exclCollections,
        excludedTags: exclTags,
        excludedItemTypes: exclItemTypes,
      });
      // Apply immediately: remove matching items from the index so users don't
      // have to reindex. (Un-excluding still needs a Sync to re-embed items.)
      try {
        const resp = await apiFetch('/api/exclusions/purge', { method: 'POST' });
        const data = await resp.json();
        if (data?.purged_items > 0) {
          setExclusionMessage(`Removed ${data.purged_items} item${data.purged_items !== 1 ? 's' : ''} from the index.`);
          await fetchStats();
        }
      } catch (err) {
        console.error('Failed to purge excluded items', err);
      }
      setExclusionsSaved(true);
      setTimeout(() => setExclusionsSaved(false), 3000);
    } catch (err) {
      console.error('Failed to save exclusions', err);
    } finally {
      setSavingExclusions(false);
    }
  };

  const handleClearExclusions = async () => {
    setExclCollections([]);
    setExclTags([]);
    setExclItemTypes([]);
    setExclusionMessage(null);
    // Persist immediately so a following Sync actually restores excluded items.
    // (Clearing only removes the rules; run Sync to re-index what was removed.)
    setSavingExclusions(true);
    try {
      await updateSettings({ excludedCollections: [], excludedTags: [], excludedItemTypes: [] });
      setExclusionMessage('Exclusions cleared — click "Sync Library" to restore any removed items.');
    } catch (err) {
      console.error('Failed to clear exclusions', err);
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
    } catch (err) {
      console.error('Failed to save embedding model', err);
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
    } catch (err) {
      console.error('Failed to fetch index stats', err);
    }
  };

  useEffect(() => {
    fetchStats();
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

  const startIndexing = async (incremental: boolean) => {
    if (indexing || indexingRef.current) return;

    indexingRef.current = true;
    setIndexing(true);

    try {
      await apiFetch("/api/index_library", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ incremental })
      });

      // Start polling status
      const poll = async () => {
        try {
          const r = await apiFetch('/api/index_status');
          const js = await r.json();
          setIndexStatus(js);

          if (js?.status === 'indexing') {
            return false;
          }

          // Refresh stats after indexing completes
          await fetchStats();
          return true;
        } catch (err) {
          console.error('Failed to fetch index_status', err);
          return true;
        }
      };

      const done = await poll();
      if (!done) {
        pollRef.current = window.setInterval(async () => {
          const finished = await poll();
          if (finished) {
            if (pollRef.current) {
              window.clearInterval(pollRef.current);
              pollRef.current = null;
            }
            setIndexing(false);
            indexingRef.current = false;
          }
        }, 1500) as unknown as number;
      } else {
        setIndexing(false);
        indexingRef.current = false;
      }
    } catch (e: any) {
      console.error("Indexing request failed", e);
      setIndexing(false);
      indexingRef.current = false;
      setIndexStatus({ status: 'error', progress: { error: 'Sync failed — check that Zotero is closed and try again.' } });
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
        setMetadataSyncSuccess(
          `Successfully synced metadata for ${result.summary?.unique_items || 0} items (${result.summary?.updated_chunks || 0} chunks updated in ${result.summary?.elapsed_seconds || 0}s)`
        );
        // Refresh stats after syncing
        await fetchStats();
      } else {
        setMetadataSyncError(result.error || 'Metadata sync failed');
      }
    } catch (err) {
      setMetadataSyncError(err instanceof Error ? err.message : 'Metadata sync failed');
    } finally {
      setSyncingMetadata(false);
    }
  };

  return (
    <>
      <header>
        <div style={{
          fontFamily: "var(--font-serif)",
          fontSize: "20px",
          fontWeight: 600,
          color: "var(--text-main)",
          letterSpacing: "0.02em",
          marginBottom: "4px"
        }}>
          Library
        </div>
        <div className="muted">Manage indexing and metadata for your Zotero library</div>
      </header>

      <main className="lib-panel">

        {/* Library Status Section */}
        <section className="lib-section">
          <h3 className="scope-section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <ellipse cx="12" cy="5" rx="9" ry="3" stroke="currentColor" strokeWidth="2"/>
              <path d="M3 5v6c0 1.66 4.03 3 9 3s9-1.34 9-3V5" stroke="currentColor" strokeWidth="2"/>
              <path d="M3 11v6c0 1.66 4.03 3 9 3s9-1.34 9-3v-6" stroke="currentColor" strokeWidth="2"/>
            </svg>
            Library Status
          </h3>

          {indexStats ? (
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-value">{indexStats.indexed_items}</div>
                <div className="stat-label">Indexed Items</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{indexStats.total_chunks}</div>
                <div className="stat-label">Total Chunks</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{indexStats.zotero_items}</div>
                <div className="stat-label">Library Items</div>
              </div>
              <div className="stat-card">
                <div className="stat-value stat-value-highlight">{indexStats.new_items}</div>
                <div className="stat-label">New Items</div>
              </div>
            </div>
          ) : (
            <div className="loading-stats">Loading stats...</div>
          )}

          {indexStats && (
            <div className="model-info">
              <strong>Embedding Model:</strong> {indexStats.current_embedding_model}
            </div>
          )}
        </section>

        {/* Embedding Model Section */}
        <section className="lib-section">
          <h3 className="scope-section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2"/>
              <path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            Embedding Model
          </h3>

          <select
            className="lib-select"
            value={embeddingModel}
            onChange={handleEmbeddingModelChange}
          >
            <optgroup label="Local (runs on this device)">
              <option value="bge-base">BAAI/bge-base-en-v1.5 (768 dim) — Best quality, slower</option>
              <option value="specter">SPECTER (768 dim) — Optimized for scientific papers</option>
              <option value="minilm-l6">all-MiniLM-L6-v2 (384 dim) — Good quality, faster</option>
              <option value="minilm-l3">paraphrase-MiniLM-L3-v2 (384 dim) — Fastest</option>
            </optgroup>
            <optgroup label="Multilingual — local, runs on this device">
              <option value="bge-m3">BAAI/bge-m3 (1024 dim) — 100+ languages incl. Chinese, ~2.3GB download</option>
              <option value="bge-large-zh">BAAI/bge-large-zh-v1.5 (1024 dim) — Chinese-optimised, ~1.3GB download</option>
              <option value="multilingual-minilm">paraphrase-multilingual-MiniLM-L12-v2 (384 dim) — 50+ languages, ~470MB download</option>
            </optgroup>
            <optgroup label="Cloud — text sent to external API">
              <option value="openai:text-embedding-3-small">OpenAI text-embedding-3-small (1536 dim) — Fast, cloud</option>
              <option value="openai:text-embedding-3-large">OpenAI text-embedding-3-large (3072 dim) — Highest quality, cloud</option>
            </optgroup>
          </select>

          <div style={{ marginTop: '10px' }}>
            <button
              className="btn-primary"
              onClick={handleSaveModel}
              disabled={savingModel || embeddingModel === settings.embeddingModel}
            >
              {savingModel ? 'Saving...' : modelSaveSuccess ? 'Saved!' : 'Save Model'}
            </button>
          </div>

          <p className="muted" style={{ fontSize: '12px', marginTop: '10px', lineHeight: '1.5', background: 'rgba(230, 160, 32, 0.06)', border: '1.5px solid rgba(230, 160, 32, 0.3)', borderRadius: '6px', padding: '10px 12px', color: '#b07820' }}>
            Changing the embedding model requires a full re-index of your library. To try a different model while keeping existing embeddings, create a new profile instead.
          </p>
        </section>

        {/* Excluded from Indexing Section */}
        <section className="lib-section">
          <h3 className="scope-section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <line x1="1" y1="1" x2="23" y2="23" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            Excluded from Indexing
          </h3>

          <p className="muted" style={{ fontSize: '12px', marginBottom: '14px', lineHeight: '1.5' }}>
            Items matching any rule below are skipped during indexing. An item is excluded if it belongs to an excluded collection or tag, or is an excluded item type — even when it is also filed in a collection you keep. Already-indexed items that become excluded are removed on your next sync.
          </p>

          {/* Axis selector */}
          <div style={{ display: 'flex', gap: '6px', marginBottom: '10px' }}>
            {exclusionAxes.map(axis => (
              <button
                key={axis.key}
                type="button"
                onClick={() => { setActiveAxis(axis.key); setExclSearch(''); }}
                style={{
                  flex: 1,
                  padding: '7px 10px',
                  fontSize: '13px',
                  fontWeight: 600,
                  borderRadius: '6px',
                  cursor: 'pointer',
                  border: '1px solid var(--border, rgba(0,0,0,0.12))',
                  background: activeAxis === axis.key ? 'var(--accent, #5b7bc5)' : 'transparent',
                  color: activeAxis === axis.key ? '#fff' : 'var(--text-main)',
                }}
              >
                {axis.label}
                {axis.selected.length > 0 && (
                  <span style={{
                    marginLeft: '6px',
                    fontSize: '11px',
                    padding: '1px 6px',
                    borderRadius: '10px',
                    background: activeAxis === axis.key ? 'rgba(255,255,255,0.25)' : 'rgba(100,130,240,0.15)',
                  }}>
                    {axis.selected.length}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Search field for the active axis */}
          <input
            type="text"
            value={exclSearch}
            onChange={e => setExclSearch(e.target.value)}
            placeholder={`Search ${activeAxisData.label.toLowerCase()}...`}
            style={{
              width: '100%',
              boxSizing: 'border-box',
              padding: '7px 10px',
              fontSize: '13px',
              marginBottom: '8px',
              borderRadius: '6px',
              border: '1px solid var(--border, rgba(0,0,0,0.12))',
              background: 'var(--input-bg, transparent)',
              color: 'var(--text-main)',
            }}
          />

          {/* Active axis list */}
          {activeAxisData.options.length === 0 ? (
            <div className="muted" style={{ fontSize: '12px' }}>None found in your library.</div>
          ) : filteredOptions.length === 0 ? (
            <div className="muted" style={{ fontSize: '12px' }}>No matches for “{exclSearch}”.</div>
          ) : (
            <div style={{ maxHeight: '220px', overflowY: 'auto', border: '1px solid var(--border, rgba(0,0,0,0.12))', borderRadius: '6px', padding: '8px 10px' }}>
              {filteredOptions.map(o => (
                <label key={o.name} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0', fontSize: '13px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={activeAxisData.selected.includes(o.name)}
                    onChange={() => toggle(activeAxisData.selected, activeAxisData.setSelected, o.name)}
                  />
                  <span style={{ flex: 1 }}>{o.name}</span>
                  {o.count != null && <span className="muted" style={{ fontSize: '11px' }}>{o.count}</span>}
                </label>
              ))}
            </div>
          )}

          {/* Summary of all exclusion rules */}
          <div style={{ marginTop: '12px', fontSize: '12px', lineHeight: '1.6' }}>
            {exclusionAxes.every(a => a.selected.length === 0) ? (
              <span className="muted">Nothing excluded — your whole library will be indexed.</span>
            ) : (
              <>
                <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>Excluding: </span>
                {exclusionAxes
                  .filter(a => a.selected.length > 0)
                  .map(a => `${a.label} (${a.selected.length}): ${a.selected.join(', ')}`)
                  .join('  ·  ')}
              </>
            )}
          </div>

          <div style={{ display: 'flex', gap: '8px', marginTop: '12px', maxWidth: '320px' }}>
            <button
              className="btn-primary"
              style={{ flex: 1 }}
              onClick={handleSaveExclusions}
              disabled={savingExclusions || !exclusionsDirty}
            >
              {savingExclusions ? 'Saving...' : exclusionsSaved ? 'Saved!' : 'Save Exclusions'}
            </button>
            <button
              className="btn-secondary"
              style={{ flex: 1 }}
              onClick={handleClearExclusions}
              disabled={savingExclusions || !hasSelections}
            >
              Clear
            </button>
          </div>

          {exclusionMessage && (
            <div className="migration-result success" style={{ marginTop: '10px' }}>
              ✓ {exclusionMessage}
            </div>
          )}
        </section>

        {/* Indexing Section */}
        <section className="lib-section">
          <h3 className="scope-section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M23 4v6h-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M1 20v-6h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Indexing
          </h3>

          <p className="muted" style={{ fontSize: '12px', marginBottom: '14px', lineHeight: '1.5' }}>
            Index your Zotero library to enable semantic search and RAG capabilities
          </p>

          <div className="lib-action-row">
            <button
              className="btn-primary"
              onClick={() => startIndexing(true)}
              disabled={indexing}
            >
              {indexing && indexStatus?.progress?.mode === 'incremental'
                ? 'Syncing...'
                : indexStats?.new_items && indexStats.new_items > 0
                  ? `Sync ${indexStats.new_items} New Item${indexStats.new_items !== 1 ? 's' : ''}`
                  : 'Sync Library'
              }
            </button>

            <button
              className="btn-secondary"
              onClick={() => startIndexing(false)}
              disabled={indexing}
            >
              {indexing && indexStatus?.progress?.mode === 'full'
                ? 'Reindexing...'
                : 'Full Reindex'
              }
            </button>

            {indexing && (
              <button
                className="lib-cancel-btn"
                onClick={stopIndexing}
              >
                {indexStatus?.progress?.mode === 'incremental' ? 'Pause' : 'Stop'}
              </button>
            )}
          </div>

          {/* Progress Display */}
          {indexStatus && indexStatus.status === 'indexing' && indexStatus.progress && !indexStatus.progress.error && (
            <div className="indexing-progress">
              <div className="progress-header">
                <span className="progress-label">
                  {indexStatus.progress.mode === 'incremental' ? 'Syncing' : 'Reindexing'}...
                </span>
                {indexStatus.progress.eta_seconds != null && indexStatus.progress.eta_seconds > 0 && (
                  <span className="progress-eta">
                    ~{indexStatus.progress.eta_seconds < 60
                      ? `${indexStatus.progress.eta_seconds}s`
                      : `${Math.ceil(indexStatus.progress.eta_seconds / 60)}m`}
                  </span>
                )}
              </div>

              <div className="progress-bar">
                {indexStatus.progress.total_items ? (
                  <div
                    className="progress-fill"
                    style={{
                      width: `${Math.min(100, Math.round((100 * (indexStatus.progress.processed_items ?? 0) / (indexStatus.progress.total_items ?? 1))))}%`
                    }}
                  />
                ) : (
                  <div className="progress-fill-indeterminate" />
                )}
              </div>

              <div className="progress-details">
                {indexStatus.progress.processed_items ?? 0} / {indexStatus.progress.total_items ?? 0} items
                {indexStatus.progress.mode === 'incremental' && (indexStatus.progress.skipped_items ?? 0) > 0 && (
                  <span> ({indexStatus.progress.skipped_items} already indexed)</span>
                )}
              </div>
            </div>
          )}

          {/* Error Display */}
          {indexStatus && indexStatus.progress?.error && (
            <div className="error-banner" style={{ marginTop: '14px', marginBottom: '10px' }}>
              <strong>Indexing Failed:</strong> {indexStatus.progress.error}
            </div>
          )}

          <p className="muted" style={{ fontSize: '12px', marginTop: '10px', lineHeight: '1.5' }}>
            <strong style={{ color: 'var(--text-main)', fontWeight: 600 }}>Sync Library:</strong> Indexes new items only — safe to interrupt and resume. Use this for your first index and for ongoing updates. &bull;{' '}
            <strong style={{ color: 'var(--text-main)', fontWeight: 600 }}>Full Reindex:</strong> Wipes and rebuilds the entire index from scratch. Only needed if your index is corrupted or you change embedding models.
          </p>

          <div className="info-box" style={{ fontSize: '12px', marginTop: '14px', lineHeight: '1.5', background: 'rgba(100, 130, 240, 0.06)', border: '1.5px solid rgba(100, 130, 240, 0.25)', borderRadius: '6px', padding: '10px 12px', color: '#5b7bc5' }}>
            <strong style={{ display: 'block', marginBottom: '4px', color: 'var(--text-main)' }}>Large libraries:</strong>
            Indexing can take a long time for large collections. If you close the app or are interrupted, just click <strong>Sync Library</strong> again — it will pick up where it left off.
          </div>
        </section>

        {/* Metadata Sync Section */}
        <section className="lib-section lib-section-last">
          <h3 className="scope-section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Metadata Sync
          </h3>

          <p className="muted" style={{ fontSize: '12px', marginBottom: '14px', lineHeight: '1.5' }}>
            Update titles, authors, tags, and other metadata from Zotero without re-embedding documents
          </p>

          <div>
            <button
              className="btn-primary"
              onClick={handleMetadataSync}
              disabled={syncingMetadata}
            >
              {syncingMetadata ? (
                <>
                  <span className="spinner" style={{ marginRight: '8px' }}></span>
                  Syncing Metadata...
                </>
              ) : (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ marginRight: '8px' }}>
                    <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Sync Metadata from Zotero
                </>
              )}
            </button>
          </div>

          {metadataSyncSuccess && (
            <div className="migration-result success" style={{ marginTop: '12px' }}>
              ✓ {metadataSyncSuccess}
            </div>
          )}

          {metadataSyncError && (
            <div className="migration-result error" style={{ marginTop: '12px' }}>
              ✗ {metadataSyncError}
            </div>
          )}

          <div className="lib-info-box" style={{ marginTop: '12px' }}>
            <div style={{ fontWeight: 600, marginBottom: '4px', fontSize: '12px' }}>When to use:</div>
            <ul style={{ margin: '4px 0', paddingLeft: '18px', fontSize: '12px', lineHeight: '1.7' }}>
              <li>You've edited titles, authors, or tags in Zotero</li>
              <li>You've changed item types or added collections</li>
              <li>You want fresh metadata without re-processing PDFs</li>
            </ul>
            <div style={{ marginTop: '8px', fontSize: '12px', opacity: 0.85 }}>
              <strong>Note:</strong> This updates metadata only. To index new PDFs, use "Sync Library" above.
            </div>
          </div>
        </section>

      </main>

      {/* Cloud embedding privacy warning modal */}
      {cloudWarningTarget && (
        <div className="cloud-warning-overlay" role="dialog" aria-modal="true">
          <div className="cloud-warning-modal">
            <div className="cloud-warning-header">
              <span className="cloud-warning-icon">⚠️</span>
              <h3>Your document text will leave this device</h3>
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
                className="btn-ghost"
                onClick={() => setCloudWarningTarget(null)}
              >
                Cancel
              </button>
              <button
                className="btn-danger"
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
    </>
  );
};

export default LibraryManagementPanel;
