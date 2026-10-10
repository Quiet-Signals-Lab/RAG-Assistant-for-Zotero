import React, { useState } from 'react';
import '../../styles/sidebar-tabs.css';

export interface TabConfig {
  id: string;
  label: string;
  icon: React.ReactNode;
  panel: React.ComponentType;
}

interface SidebarTabsProps {
  tabs: TabConfig[];
  defaultTab: string;
  activeTab?: string;
  onTabChange?: (tabId: string) => void;
}

const SidebarTabs: React.FC<SidebarTabsProps> = ({ 
  tabs, 
  defaultTab, 
  activeTab: controlledActiveTab,
  onTabChange 
}) => {
  const [internalActiveTab, setInternalActiveTab] = useState(defaultTab);
  
  // Use controlled tab if provided, otherwise use internal state
  const activeTab = controlledActiveTab !== undefined ? controlledActiveTab : internalActiveTab;
  
  const handleTabClick = (tabId: string) => {
    if (controlledActiveTab === undefined) {
      setInternalActiveTab(tabId);
    }
    onTabChange?.(tabId);
  };
  
  const activeTabConfig = tabs.find(tab => tab.id === activeTab);
  const ActivePanel = activeTabConfig?.panel;
  
  return (
    <div className="sidebar-tabs">
      {/* Icon navigation on the left edge */}
      <nav className="sidebar-tabs__nav">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`sidebar-tabs__nav-item ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => handleTabClick(tab.id)}
            title={tab.label}
            aria-label={tab.label}
          >
            {tab.icon}
          </button>
        ))}
      </nav>
      
      {/* Content area */}
      <div className="sidebar-tabs__content">
        {ActivePanel && <ActivePanel />}
      </div>
    </div>
  );
};

export default SidebarTabs;
