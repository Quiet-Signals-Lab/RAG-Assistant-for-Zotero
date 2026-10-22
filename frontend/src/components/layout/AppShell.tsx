import React from "react";
import { useSettings } from "../../contexts/SettingsContext";
import DeskShell from "../../features/desk/DeskShell";
import "../../styles/layout.css";

/** One shell for both modes; the mode only changes what the three panes hold. */
const AppShell: React.FC = () => {
  const { loading } = useSettings();
  if (loading) return null; // the mode is read from settings, so wait for it rather than flash the wrong one
  return <DeskShell />;
};

export default AppShell;
