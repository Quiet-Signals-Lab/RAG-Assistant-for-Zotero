import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { request } from "../../api/client";
import { deskModel } from "../../api/search";
import type { DeskModel } from "../../types/desk";
import LibraryManagementPanel from "../library/LibraryManagementPanel";
import { getElectronAPI } from "../../utils/electron";
import Bibliography from "./Bibliography";
import ClerkRoom from "./ClerkRoom";
import { useDesk, type Pane, type Room } from "./DeskContext";
import Evidence from "./Evidence";
import QueryDesk from "./QueryDesk";
import RoomHeader from "../../components/layout/RoomHeader";
import buyMeACoffee from "../../assets/buymeacoffee.png";

type IndexStats = { indexed_items: number; total_chunks: number; current_embedding_model: string };

const REPO = "https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero";

const icons: Record<Room, React.ReactNode> = {
  desk: <><rect x="3" y="5" width="18" height="14" rx="1" /><path d="M3 9h18M7 13h7" /></>,
  library: <path d="M4 4h4v16H4zM10 4h4v16h-4zM16 6l4-1 3 15-4 1z" />,
  clerk: <><rect x="7" y="7" width="10" height="10" rx="1.5" /><rect x="10" y="10" width="4" height="4" /><path d="M10 7V3M14 7V3M10 21v-4M14 21v-4M7 10H3M7 14H3M21 10h-4M21 14h-4" /></>,
  about: <path d="M12 20.5S4 15.5 4 9.6A4.4 4.4 0 0 1 12 7a4.4 4.4 0 0 1 8 2.6c0 5.9-8 10.9-8 10.9z" />,
};
const roomLabels: Record<Room, string> = { desk: "Search", library: "Library and index", clerk: "Language model", about: "About" };

/** The QSL signal: "received", in Morse. The only place the lab signs the app. */
const QslLine: React.FC = () => (
  <svg viewBox="0 0 33 1" width="132" height="4" shapeRendering="crispEdges" role="img" aria-label="QSL in Morse code" className="qsl">
    {[[0, 3], [4, 3], [8, 1], [10, 3]].map(([x, w]) => <rect key={`q${x}`} x={x} width={w} height="1" className="qsl__ink" />)}
    {[16, 18, 20].map((x) => <rect key={`s${x}`} x={x} width="1" height="1" className="qsl__stamp" />)}
    {[[24, 1], [26, 3], [30, 1], [32, 1]].map(([x, w]) => <rect key={`l${x}`} x={x} width={w} height="1" className="qsl__ink" />)}
  </svg>
);

const About: React.FC = () => {
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    getElectronAPI()?.getAppVersion().then(setVersion).catch(() => undefined);
  }, []);
  return (
    <div className="about">
      <div className="panel-head"><h2 className="panel-head__title">About</h2></div>
      <div className="about__mark" aria-hidden="true" />
      <h2 className="about__name">RAG Assistant for Zotero</h2>
      <p className="mono about__meta">{version ? `Version ${version} · ` : ""}Made by Quiet Signals Lab in the Netherlands</p>
      <QslLine />
      <p className="about__links">
        <a href="https://quietsignalslab.com/" target="_blank" rel="noreferrer">Website</a>
        <a href="https://www.linkedin.com/company/quiet-signals-lab" target="_blank" rel="noreferrer">LinkedIn</a>
        <a href="mailto:support@quietsignalslab.com" target="_blank" rel="noreferrer">support@quietsignalslab.com</a>
        <a href={REPO} target="_blank" rel="noreferrer">Source code</a>
        <a href={`${REPO}/blob/master/docs/REFERENCE_DESK_PLAN.md`} target="_blank" rel="noreferrer">Design rationale and sources</a>
      </p>
      <p>RAG Assistant is made by a small independent software studio. It is and will remain free. If you find my work useful, please consider supporting it via the link below.</p>
      <p>
        <a href="https://buymeacoffee.com/aahepburn" target="_blank" rel="noreferrer">
          <img src={buyMeACoffee} alt="Buy Me A Coffee" height="40" />
        </a>
      </p>
      <p className="about__credit">
        The design borrows its methods from library science: Cutter's catalogue, Ranganathan's five laws, Taylor's reference
        interview and Bates' berrypicking.
      </p>
      <p className="about__credit">
        © 2025–2026 Alexander Hepburn · Licensed under the{" "}
        <a href="https://www.gnu.org/licenses/gpl-3.0.html" target="_blank" rel="noreferrer">GNU General Public License v3.0</a>.
        You may share and modify it under the same licence; it comes with no warranty.
      </p>
    </div>
  );
};

const PANES: { id: Pane; label: string }[] = [
  { id: "ask", label: "Search" },
  { id: "browse", label: "Results" },
  { id: "verify", label: "Evidence" },
];

const DeskShell: React.FC = () => {
  const desk = useDesk();
  const navigate = useNavigate();
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [clerk, setClerk] = useState<DeskModel | null>(null);

  useEffect(() => {
    request<IndexStats>("/api/index_stats").then(setStats).catch(() => setStats(null));
    deskModel().then(setClerk).catch(() => setClerk(null));
  }, [desk.room]);

  return (
    <div className="desk" data-pane={desk.pane}>
      <RoomHeader title="RAG Assistant for Zotero">
        <nav className="desk__panes" aria-label="Panels">
          {PANES.map((p) => (
            <button key={p.id} type="button" aria-pressed={desk.pane === p.id} onClick={() => desk.setPane(p.id)}>
              {p.label}
            </button>
          ))}
        </nav>
        <div className="room-header__fill" />
        {stats && (
          <span className="desk__index mono" title="What can be searched">
            {stats.indexed_items.toLocaleString()} items · {stats.total_chunks.toLocaleString()} passages · {stats.current_embedding_model}
          </span>
        )}
        {clerk && (
          <button
            type="button"
            className="desk__clerk mono"
            onClick={() => desk.setRoom("clerk")}
            title={clerk.available ? `Language model in use: ${clerk.model}` : "No language model set up: search works without one"}
          >
            {clerk.available
              ? `model · ${clerk.model.split("/").pop()}${clerk.measured ? "" : " (unmeasured)"}${desk.clerk.working ? " · working" : ""}`
              : "no model"}
          </button>
        )}
        <button type="button" className="icon-button" aria-label="Settings" onClick={() => navigate("/settings")}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
          </svg>
        </button>
      </RoomHeader>

      <div className="desk__body">
        <nav className="desk__rail" aria-label="Sections">
          {(Object.keys(icons) as Room[]).map((room) => (
            <button
              key={room}
              type="button"
              className="icon-button"
              aria-label={roomLabels[room]}
              title={roomLabels[room]}
              aria-current={desk.room === room ? "page" : undefined}
              onClick={() => {
                desk.setRoom(room);
                desk.setPane("ask");
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
                {icons[room]}
              </svg>
            </button>
          ))}
        </nav>

        <aside className="desk__ask" aria-label={roomLabels[desk.room]}>
          {desk.room === "desk" && <QueryDesk />}
          {desk.room === "library" && <LibraryManagementPanel />}
          {desk.room === "clerk" && <ClerkRoom />}
          {desk.room === "about" && <About />}
        </aside>

        <main className="desk__browse">
          <Bibliography indexEmpty={stats?.indexed_items === 0} />
        </main>

        <aside className="desk__verify" aria-label="Evidence">
          <Evidence />
        </aside>
      </div>
    </div>
  );
};

export default DeskShell;
