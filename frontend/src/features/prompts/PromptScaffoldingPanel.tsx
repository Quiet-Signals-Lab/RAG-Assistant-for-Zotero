import React, { useState, useEffect } from "react";
import { apiFetch } from "../../api/client";
import { useSearchSettings } from "../../contexts/SearchSettingsContext";
import "../../styles/prompt-scaffolding.css";

/**
 * PromptScaffoldingPanel allows users to filter the database
 * by Zotero tags and other metadata for scoped searching.
 * 
 * Features:
 * - Search engine mode toggle (original vs metadata-aware)
 * - Filter mode toggle (auto-extract vs manual specification)
 * - Manual filter controls for tags, collections, and year range
 */
const PromptScaffoldingPanel: React.FC = () => {
  const { searchSettings, updateSearchSettings, updateManualFilters, resetFilters, hasActiveFilters } = useSearchSettings();
  
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [availableTags, setAvailableTags] = useState<string[]>([]);
  const [loadingTags, setLoadingTags] = useState(false);
  const [tagError, setTagError] = useState<string | null>(null);
  const [tagSearchQuery, setTagSearchQuery] = useState<string>('');
  
  const [selectedCollections, setSelectedCollections] = useState<string[]>([]);
  const [availableCollections, setAvailableCollections] = useState<Array<{name: string, count: number}>>([]);
  const [loadingCollections, setLoadingCollections] = useState(false);
  const [collectionSearchQuery, setCollectionSearchQuery] = useState<string>('');
  
  const [yearStart, setYearStart] = useState<string>('');
  const [yearEnd, setYearEnd] = useState<string>('');
  const [itemTypeFilter, setItemTypeFilter] = useState<string[]>([]);
  const [availableItemTypes, setAvailableItemTypes] = useState<Array<{name: string, count: number}>>([]);
  const [loadingItemTypes, setLoadingItemTypes] = useState(false);
  const [titleFilter, setTitleFilter] = useState<string>('');
  const [authorFilter, setAuthorFilter] = useState<string>('');
  
  // State for filtered item count
  const [estimatedItemCount, setEstimatedItemCount] = useState<number>(0);
  const [loadingCount, setLoadingCount] = useState<boolean>(false);
  const [countError, setCountError] = useState<string | null>(null);
  
  // Load available tags, collections, and item types from backend
  useEffect(() => {
    loadAvailableTags();
    loadAvailableCollections();
    loadAvailableItemTypes();
  }, []);
  
  // Initialize local state from context on mount (restore filters when switching tabs)
  useEffect(() => {
    const { manualFilters } = searchSettings;
    setSelectedTags(manualFilters.tags || []);
    setSelectedCollections(manualFilters.collections || []);
    setYearStart(manualFilters.yearMin ? String(manualFilters.yearMin) : '');
    setYearEnd(manualFilters.yearMax ? String(manualFilters.yearMax) : '');
    setTitleFilter(manualFilters.title || '');
    setAuthorFilter(manualFilters.author || '');
    setItemTypeFilter(manualFilters.itemTypes || []);
  }, []); // Only run on mount
  
  const loadAvailableTags = async () => {
    setLoadingTags(true);
    setTagError(null);
    try {
      const response = await apiFetch('/api/library/tags');
      const data = await response.json();
      
      if (data.tags) {
        setAvailableTags(data.tags);
      } else if (data.error) {
        setTagError(data.error);
      }
    } catch (err) {
      console.error('Failed to load tags:', err);
      setTagError('Failed to load tags from library');
    } finally {
      setLoadingTags(false);
    }
  };
  
  const loadAvailableCollections = async () => {
    setLoadingCollections(true);
    try {
      const response = await apiFetch('/api/library/collections');
      const data = await response.json();
      
      if (data.collections) {
        setAvailableCollections(data.collections);
      }
    } catch (err) {
      console.error('Failed to load collections:', err);
    } finally {
      setLoadingCollections(false);
    }
  };
  
  const loadAvailableItemTypes = async () => {
    setLoadingItemTypes(true);
    try {
      const response = await apiFetch('/api/library/item_types');
      const data = await response.json();
      
      if (data.item_types) {
        setAvailableItemTypes(data.item_types);
      }
    } catch (err) {
      console.error('Failed to load item types:', err);
    } finally {
      setLoadingItemTypes(false);
    }
  };
  
  const handleTagToggle = (tag: string) => {
    setSelectedTags(prev => 
      prev.includes(tag) 
        ? prev.filter(t => t !== tag)
        : [...prev, tag]
    );
  };
  
  const handleCollectionToggle = (collection: string) => {
    setSelectedCollections(prev =>
      prev.includes(collection)
        ? prev.filter(c => c !== collection)
        : [...prev, collection]
    );
  };
  
  const handleClearFilters = () => {
    setSelectedTags([]);
    setSelectedCollections([]);
    setYearStart('');
    setYearEnd('');
    setItemTypeFilter([]);
    setTitleFilter('');
    setAuthorFilter('');
    setTagSearchQuery('');
    setCollectionSearchQuery('');
    resetFilters();
  };
  
  // Filter tags and collections based on search queries
  const filteredTags = availableTags.filter(tag => 
    tag.toLowerCase().includes(tagSearchQuery.toLowerCase())
  );
  
  const filteredCollections = availableCollections.filter(collection =>
    collection.name.toLowerCase().includes(collectionSearchQuery.toLowerCase())
  );
  
  const handleApplyFilters = () => {
    // Update manual filters in context
    updateManualFilters({
      yearMin: yearStart ? parseInt(yearStart) : undefined,
      yearMax: yearEnd ? parseInt(yearEnd) : undefined,
      tags: selectedTags,
      collections: selectedCollections,
      title: titleFilter || undefined,
      author: authorFilter || undefined,
      itemTypes: itemTypeFilter.length > 0 ? itemTypeFilter : undefined,
    });
  };
  
  const handleSearchModeChange = (mode: 'original' | 'metadata-aware') => {
    updateSearchSettings({ searchEngineMode: mode });
  };
  
  const handleFilterModeChange = (mode: 'auto' | 'manual') => {
    updateSearchSettings({ filterMode: mode });
  };
  
  // Check if manual filters are enabled
  const isManualMode = searchSettings.filterMode === 'manual';
  const isMetadataAware = searchSettings.searchEngineMode === 'metadata-aware';
  
  // Fetch estimated count of filtered items whenever filters change
  useEffect(() => {
    if (!isMetadataAware || !isManualMode) {
      setEstimatedItemCount(0);
      return;
    }
    
    const fetchCount = async () => {
      setLoadingCount(true);
      try {
        const response = await apiFetch('/api/metadata/count_filtered', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            year_min: yearStart ? parseInt(yearStart) : undefined,
            year_max: yearEnd ? parseInt(yearEnd) : undefined,
            tags: selectedTags.length > 0 ? selectedTags : undefined,
            collections: selectedCollections.length > 0 ? selectedCollections : undefined,
            title: titleFilter || undefined,
            author: authorFilter || undefined,
            item_types: itemTypeFilter.length > 0 ? itemTypeFilter : undefined,
          }),
        });
        
        const data = await response.json();
        if (data.unique_items !== undefined) {
          setEstimatedItemCount(data.unique_items);
          setCountError(null);
        } else {
          // Keeping the previous number here made a failed filter look exactly
          // like "no filter applied" (issue #75) — surface it instead.
          setEstimatedItemCount(0);
          setCountError(data.error || 'Could not count items for this filter');
        }
      } catch (err) {
        console.error('Failed to fetch filtered item count:', err);
        setEstimatedItemCount(0);
        setCountError(err instanceof Error ? err.message : 'Could not reach the backend');
      } finally {
        setLoadingCount(false);
      }
    };
    
    fetchCount();
  }, [selectedTags, selectedCollections, yearStart, yearEnd, titleFilter, authorFilter, itemTypeFilter, isMetadataAware, isManualMode]);
  
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
          Scope
        </div>
        <div className="muted">Filter library for targeted queries</div>
      </header>
      
      <main className="scope-panel">
        {/* Search Engine Mode Toggle */}
        <section className="scope-section">
          <h3 className="scope-section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2"/>
              <path d="M12 1v6m0 6v6M23 12h-6m-6 0H1" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            Search Engine Mode
          </h3>
          <div className="toggle-group">
            <button
              className={`toggle-btn ${!isMetadataAware ? 'active' : ''}`}
              onClick={() => handleSearchModeChange('original')}
            >
              Semantic only
            </button>
            <button
              className={`toggle-btn ${isMetadataAware ? 'active' : ''}`}
              onClick={() => handleSearchModeChange('metadata-aware')}
            >
              Metadata-Aware
            </button>
          </div>
          <p className="muted" style={{ fontSize: '12px', marginTop: '12px', lineHeight: '1.5' }}>
            {!isMetadataAware 
              ? 'Wide net search with no filters — casts the broadest possible search across your entire library. Returns fewer chunks per paper to maximize coverage across documents.'
              : 'Smart filtering by tags, collections, and publication dates for precise results'}
          </p>
        </section>
        
        {/* Filter Mode Toggle (only shown in metadata-aware mode) */}
        {isMetadataAware && (
          <section className="scope-section">
            <h3 className="scope-section-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Filter Mode
            </h3>
            <div className="toggle-group">
              <button
                className={`toggle-btn ${!isManualMode ? 'active' : ''}`}
                onClick={() => handleFilterModeChange('auto')}
              >
                Auto-Extract
              </button>
              <button
                className={`toggle-btn ${isManualMode ? 'active' : ''}`}
                onClick={() => handleFilterModeChange('manual')}
              >
                Manual
              </button>
            </div>
            <p className="muted" style={{ fontSize: '12px', marginTop: '12px', lineHeight: '1.5' }}>
              {!isManualMode
                ? 'Filters extracted automatically from queries (e.g., "papers after 2020 about machine learning")'
                : 'Define filters manually using the controls below for maximum precision'}
            </p>
          </section>
        )}
        
        {/* Only show manual filter controls in manual mode */}
        {isMetadataAware && isManualMode && (
          <>
        {/* Tags Section */}
        <section className="scope-section">
          <h3 className="scope-section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="7" cy="7" r="1" fill="currentColor"/>
            </svg>
            Tags
            {selectedTags.length > 0 && (
              <span className="filter-badge">{selectedTags.length}</span>
            )}
          </h3>
          
          <div className="tag-filter">
            {/* Search Input */}
            <div className="search-input-wrapper">
              <svg className="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2"/>
                <path d="m21 21-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              <input
                type="text"
                className="search-input"
                placeholder="Search tags..."
                value={tagSearchQuery}
                onChange={(e) => setTagSearchQuery(e.target.value)}
              />
              {tagSearchQuery && (
                <button 
                  className="search-clear"
                  onClick={() => setTagSearchQuery('')}
                  title="Clear search"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                </button>
              )}
            </div>
            
            {loadingTags && (
              <div className="scope-loading">Loading tags...</div>
            )}
            
            {tagError && (
              <div className="scope-error">{tagError}</div>
            )}
            
            {!loadingTags && !tagError && filteredTags.length > 0 && (
              <div className="tag-list">
                {filteredTags.map(tag => (
                  <button
                    key={tag}
                    className={`tag-item ${selectedTags.includes(tag) ? 'selected' : ''}`}
                    onClick={() => handleTagToggle(tag)}
                  >
                    <span className="tag-text">{tag}</span>
                    {selectedTags.includes(tag) && (
                      <svg className="tag-check" width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </button>
                ))}
              </div>
            )}
            
            {!loadingTags && !tagError && filteredTags.length === 0 && availableTags.length > 0 && (
              <div className="scope-empty">
                <p>No tags match "{tagSearchQuery}"</p>
              </div>
            )}
            
            {!loadingTags && !tagError && availableTags.length === 0 && (
              <div className="scope-empty">
                <p>No tags found in your library</p>
              </div>
            )}
          </div>
        </section>
        
        {/* Collections Section */}
        <section className="scope-section">
          <h3 className="scope-section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Collections
            {selectedCollections.length > 0 && (
              <span className="filter-badge">{selectedCollections.length}</span>
            )}
          </h3>
          
          <div className="collection-filter">
            {/* Search Input */}
            <div className="search-input-wrapper">
              <svg className="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2"/>
                <path d="m21 21-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              <input
                type="text"
                className="search-input"
                placeholder="Search collections..."
                value={collectionSearchQuery}
                onChange={(e) => setCollectionSearchQuery(e.target.value)}
              />
              {collectionSearchQuery && (
                <button 
                  className="search-clear"
                  onClick={() => setCollectionSearchQuery('')}
                  title="Clear search"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                </button>
              )}
            </div>
            
            {loadingCollections && (
              <div className="scope-loading">Loading collections...</div>
            )}
            
            {!loadingCollections && filteredCollections.length > 0 && (
              <div className="collection-list">
                {filteredCollections.map(collection => (
                  <button
                    key={collection.name}
                    className={`collection-item ${selectedCollections.includes(collection.name) ? 'selected' : ''}`}
                    onClick={() => handleCollectionToggle(collection.name)}
                  >
                    <span className="collection-name">{collection.name}</span>
                    <span className="collection-count">{collection.count}</span>
                  </button>
                ))}
              </div>
            )}
            
            {!loadingCollections && filteredCollections.length === 0 && availableCollections.length > 0 && (
              <div className="scope-empty">
                <p>No collections match "{collectionSearchQuery}"</p>
              </div>
            )}
            
            {!loadingCollections && availableCollections.length === 0 && (
              <div className="scope-empty">
                <p>No collections found</p>
              </div>
            )}
          </div>
        </section>
        
        {/* Date Range Section */}
        <section className="scope-section">
          <h3 className="scope-section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="3" y="4" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="2"/>
              <path d="M16 2v4M8 2v4M3 10h18" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            Publication Year
          </h3>
          
          <div className="date-range-filter">
            <input 
              type="number" 
              placeholder="From (e.g., 2020)"
              value={yearStart}
              onChange={(e) => setYearStart(e.target.value)}
              min="1900"
              max="2100"
              style={{ flex: 1 }}
            />
            <span style={{ color: 'var(--text-muted)', padding: '0 8px' }}>-</span>
            <input 
              type="number" 
              placeholder="To (e.g., 2024)"
              value={yearEnd}
              onChange={(e) => setYearEnd(e.target.value)}
              min="1900"
              max="2100"
              style={{ flex: 1 }}
            />
          </div>
        </section>
        
        {/* Text Filters Section (Title & Author combined) */}
        <section className="scope-section">
          <h3 className="scope-section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            Text Filters
          </h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div className="text-filter">
              <input
                type="text"
                className="text-filter-input"
                placeholder="Title keywords..."
                value={titleFilter}
                onChange={(e) => setTitleFilter(e.target.value)}
              />
              {titleFilter && (
                <button 
                  className="filter-clear-btn"
                  onClick={() => setTitleFilter('')}
                  title="Clear title filter"
                >
                  ×
                </button>
              )}
            </div>
            
            <div className="text-filter">
              <input
                type="text"
                className="text-filter-input"
                placeholder="Author name..."
                value={authorFilter}
                onChange={(e) => setAuthorFilter(e.target.value)}
              />
              {authorFilter && (
                <button 
                  className="filter-clear-btn"
                  onClick={() => setAuthorFilter('')}
                  title="Clear author filter"
                >
                  ×
                </button>
              )}
            </div>
          </div>
        </section>
        
        {/* Item Type Section */}
        <section className="scope-section">
          <h3 className="scope-section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="2"/>
              <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            Item Type
            {itemTypeFilter.length > 0 && (
              <span className="filter-badge">{itemTypeFilter.length}</span>
            )}
          </h3>
          
          <div className="item-type-filter">
            {loadingItemTypes ? (
              <div className="loading-message">Loading item types...</div>
            ) : availableItemTypes.length === 0 ? (
              <div className="empty-message">No item types found</div>
            ) : (
              <div className="item-type-list">
                {availableItemTypes.map(({name, count}) => {
                  // Map internal names to display names
                  const displayNameMap: Record<string, string> = {
                    'journalArticle': 'Journal Article',
                    'book': 'Book',
                    'bookSection': 'Book Section',
                    'conferencePaper': 'Conference Paper',
                    'thesis': 'Thesis',
                    'preprint': 'Preprint',
                    'webpage': 'Web Page',
                    'report': 'Report',
                    'presentation': 'Presentation',
                    'manuscript': 'Manuscript',
                  };
                  const displayName = displayNameMap[name] || name.charAt(0).toUpperCase() + name.slice(1);
                  
                  return (
                    <label key={name} className="item-type-checkbox">
                      <input
                        type="checkbox"
                        checked={itemTypeFilter.includes(name)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setItemTypeFilter(prev => [...prev, name]);
                          } else {
                            setItemTypeFilter(prev => prev.filter(t => t !== name));
                          }
                        }}
                      />
                      <span>{displayName} ({count})</span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        </section>
        </>
        )}
        
        {/* Preview/Apply Section */}
        <div className="scope-actions">
          {isMetadataAware && isManualMode && (
            <>
              <div className="scope-preview">
                <span className="muted">Approximately</span>
                <strong>{loadingCount ? '...' : estimatedItemCount}</strong>
                <span className="muted">items in scope</span>
              </div>
              
              {countError && (
                <p className="scope-note" style={{ color: 'var(--danger)' }}>
                  Could not count items in scope: {countError}
                </p>
              )}
              
              {!loadingCount && !countError && estimatedItemCount === 0 && hasActiveFilters() && (
                <p className="scope-note muted">
                  No indexed items match. Scope filters run on metadata captured when
                  items were indexed, so tags or collections you changed in Zotero
                  since then won't match until you sync metadata in Settings.
                </p>
              )}
              
              {(selectedTags.length > 0 || selectedCollections.length > 0 || yearStart || yearEnd || titleFilter || authorFilter || itemTypeFilter.length > 0) && (
                <button 
                  className="btn-secondary"
                  onClick={handleClearFilters}
                >
                  Clear All Filters
                </button>
              )}
              
              <button 
                className="btn-primary"
                onClick={handleApplyFilters}
              >
                Apply Filters to Search
              </button>
              
              {hasActiveFilters() && (
                <p className="scope-note" style={{ color: 'var(--success)' }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                    <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                  Filters are active! Your searches will be constrained to the selected scope.
                </p>
              )}
            </>
          )}
          
          {!isMetadataAware && (
            <p className="scope-note">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                <path d="M12 16v-4M12 8h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              Enable "Metadata-Aware Search" above to use filtering features.
            </p>
          )}
          
          {isMetadataAware && !isManualMode && (
            <p className="scope-note">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                <path d="M12 8v4l2 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              Auto-extract mode is active. Filters will be extracted automatically from your queries.
            </p>
          )}
        </div>
      </main>
    </>
  );
};

export default PromptScaffoldingPanel;
