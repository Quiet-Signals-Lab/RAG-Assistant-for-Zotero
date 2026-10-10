import React from "react";
import ChatView from "../../features/chat/ChatView";
import SourcesPanel from "../../features/sources/SourcesPanel";
import SnippetsPanel from "../../features/sessions/SnippetsPanel";
import PromptScaffoldingPanel from "../../features/prompts/PromptScaffoldingPanel";
import ActiveModelPanel from "../../features/models/ActiveModelPanel";
import LibraryManagementPanel from "../../features/library/LibraryManagementPanel";
import SidebarTabs, { TabConfig } from "./SidebarTabs";
import TopNav from "./TopNav";
import "../../styles/layout.css";
import "../../styles/sidebar-tabs.css";
import { useSessions } from "../../contexts/SessionsContext";
import { useSettings } from "../../contexts/SettingsContext";
import DeskShell from "../../features/desk/DeskShell";

const AppShell: React.FC = () => {
  const { settings, loading } = useSettings();
  if (loading) return null; // avoid flashing the desk for someone who chose legacy chat
  return settings.interfaceMode === "chat" ? <LegacyChatShell /> : <DeskShell />;
};

/** The legacy chat interface, kept behind Settings → Interface. Not developed further. */
const LegacyChatShell: React.FC = () => {
  const { leftCollapsed, rightCollapsed, leftActiveTab, setLeftActiveTab } = useSessions();
  const classes = ["app-shell", leftCollapsed ? "app-shell--left-collapsed" : "", rightCollapsed ? "app-shell--right-collapsed" : ""].join(" ");

  // Define left sidebar tabs
  const leftTabs: TabConfig[] = [
    {
      id: 'evidence',
      label: 'Evidence',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      ),
      panel: SnippetsPanel
    },
    {
      id: 'scope',
      label: 'Scope',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="m21 21-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M11 8v6M8 11h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      ),
      panel: PromptScaffoldingPanel
    },
    {
      id: 'library',
      label: 'Library',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M2 17l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      ),
      panel: LibraryManagementPanel
    },
    {
      id: 'model',
      label: 'Model',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="9" y="9" width="6" height="6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M9 1v6M15 1v6M9 17v6M15 17v6M1 9h6M1 15h6M17 9h6M17 15h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      ),
      panel: ActiveModelPanel
    }
  ];

  return (
    <>
      <TopNav />
      <div className={classes}>
        <aside className="app-shell__sidebar">
          <SidebarTabs 
            tabs={leftTabs} 
            defaultTab="evidence"
            activeTab={leftActiveTab}
            onTabChange={setLeftActiveTab}
          />
        </aside>
        <main className="app-shell__main">
          <ChatView />
        </main>
        <section className="app-shell__sources">
          <SourcesPanel />
        </section>
      </div>
    </>
  );
};

export default AppShell;
