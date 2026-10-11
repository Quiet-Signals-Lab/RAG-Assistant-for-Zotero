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

type IndexStats = { indexed_items: number; total_chunks: number; current_embedding_model: string };

const REPO = "https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero";

const icons: Record<Room, React.ReactNode> = {
  desk: <><rect x="3" y="5" width="18" height="14" rx="1" /><path d="M3 9h18M7 13h7" /></>,
  library: <path d="M4 4h4v16H4zM10 4h4v16h-4zM16 6l4-1 3 15-4 1z" />,
  clerk: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20c1-4 4-6 7-6s6 2 7 6M3 20h18" /></>,
  about: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
};
const roomLabels: Record<Room, string> = { desk: "Desk", library: "Library and index", clerk: "Desk clerk (model)", about: "About" };

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
      <div className="panel-head"><span className="panel-head__title">About</span></div>
      <div className="about__mark" aria-hidden="true" />
      <h2 className="about__name">RAG Assistant for Zotero</h2>
      <p>A reference desk for your Zotero library. Ranked sources with the evidence open at the page. No answers. Nothing leaves this computer unless you set it to.</p>
      <p className="mono about__meta">{version ? `Version ${version} · ` : ""}Free and open source · Made by Quiet Signals Lab</p>
      <QslLine />
      <h3 className="desk-label">What this desk will never do</h3>
      <ul className="about__never">
        <li>Answer your question for you, or write a summary across papers.</li>
        <li>Send your PDFs anywhere.</li>
        <li>Write to your Zotero database.</li>
        <li>Require an account or an API key.</li>
      </ul>
      <p className="about__links">
        <a href={REPO} target="_blank" rel="noreferrer">Source code</a>
        <a href={`${REPO}/blob/master/docs/REFERENCE_DESK_PLAN.md`} target="_blank" rel="noreferrer">Design rationale and sources</a>
      </p>
      <p className="about__credit">
        The desk borrows its methods from library science: Cutter's catalogue, Ranganathan's five laws, Taylor's reference
        interview and Bates' berrypicking. It does the catalogue's job, not the librarian's.
      </p>
    </div>
  );
};

const PANES: { id: Pane; label: string }[] = [
  { id: "ask", label: "Ask" },
  { id: "browse", label: "Browse" },
  { id: "verify", label: "Verify" },
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
      <RoomHeader title="Reference desk">
        <nav className="desk__panes" aria-label="Panes">
          {PANES.map((p) => (
            <button key={p.id} type="button" aria-pressed={desk.pane === p.id} onClick={() => desk.setPane(p.id)}>
              {p.label}
            </button>
          ))}
        </nav>
        <div className="room-header__fill" />
        {stats && (
          <span className="desk__index mono" title="What the desk can search">
            {stats.indexed_items.toLocaleString()} items · {stats.total_chunks.toLocaleString()} passages · {stats.current_embedding_model}
          </span>
        )}
        {clerk && (
          <button
            type="button"
            className="desk__clerk mono"
            onClick={() => desk.setRoom("clerk")}
            title={clerk.available ? `The desk clerk uses ${clerk.model}` : "No model: the desk works on its own"}
          >
            {clerk.available
              ? `clerk · ${clerk.model.split("/").pop()}${clerk.measured ? "" : " (unmeasured)"}${desk.clerk.working ? " · working" : ""}`
              : "no clerk"}
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
        <nav className="desk__rail" aria-label="Rooms">
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
