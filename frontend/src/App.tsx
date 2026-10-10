// src/App.tsx
import React from "react";
import { HashRouter as Router, Routes, Route } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import Settings from "./pages/Settings";
import "./styles/globals.css";
import "./styles/theme.css";
import { ChatProvider } from "./contexts/ChatContext";
import { SessionsProvider } from "./contexts/SessionsContext";
import { ResponseSelectionProvider } from "./contexts/ResponseSelectionContext";
import { SettingsProvider } from "./contexts/SettingsContext";
import { ProfileProvider } from "./contexts/ProfileContext";
import { SearchSettingsProvider } from "./contexts/SearchSettingsContext";
import { DeskProvider } from "./features/desk/DeskContext";

const App: React.FC = () => (
	<Router>
		<ProfileProvider>
			<SettingsProvider>
				<SearchSettingsProvider>
						<SessionsProvider>
							<ResponseSelectionProvider>
								<ChatProvider>
									<DeskProvider>
										<Routes>
											<Route path="/" element={<AppShell />} />
											<Route path="/settings" element={<Settings />} />
										</Routes>
									</DeskProvider>
								</ChatProvider>
							</ResponseSelectionProvider>
						</SessionsProvider>
				</SearchSettingsProvider>
			</SettingsProvider>
		</ProfileProvider>
	</Router>
);

export default App;
