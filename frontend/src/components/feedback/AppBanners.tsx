import React, { useEffect, useState } from "react";
import { apiFetch, BACKEND_BACK, BACKEND_DOWN, BACKEND_UNREACHABLE } from "../../api/client";
import { useProfile } from "../../contexts/ProfileContext";
import { useSessions } from "../../contexts/SessionsContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useDesk } from "../../features/desk/DeskContext";
import ErrorBanner from "./ErrorBanner";

/** What went wrong and has no place of its own, over every screen. */
const AppBanners: React.FC = () => {
  const [down, setDown] = useState(false);
  const settings = useSettings();
  const profile = useProfile();
  const { loadFailed: sessionsFailed } = useSessions();
  const { fileStatus } = useDesk();

  useEffect(() => {
    const onDown = () => setDown(true);
    window.addEventListener(BACKEND_UNREACHABLE, onDown);
    return () => window.removeEventListener(BACKEND_UNREACHABLE, onDown);
  }, []);

  // Poll only while the backend is down; what failed to load retries on BACKEND_BACK.
  useEffect(() => {
    if (!down) return;
    let live = true;
    const timer = window.setInterval(() => {
      apiFetch("/health")
        .then(() => {
          if (!live) return;
          setDown(false);
          window.dispatchEvent(new Event(BACKEND_BACK));
        })
        .catch(() => undefined);
    }, 5000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [down]);

  // The context errors repeat BACKEND_DOWN while the first banner says it.
  const show = (error: string | null) => !!error && error !== BACKEND_DOWN;
  return (
    <div className="app-banners" role="alert">
      {down && <ErrorBanner message={BACKEND_DOWN} />}
      {show(settings.error) && <ErrorBanner message={settings.error!} onDismiss={settings.clearError} />}
      {show(profile.error) && <ErrorBanner message={profile.error!} onDismiss={profile.clearError} />}
      {!down && sessionsFailed && <ErrorBanner message="Your saved sessions could not be read. New answers will not be saved until they can." />}
      {!down && fileStatus === "failed" && (
        <ErrorBanner message="Your pins, recent searches and context could not be read. Changes will not be saved until they can." />
      )}
    </div>
  );
};

export default AppBanners;
