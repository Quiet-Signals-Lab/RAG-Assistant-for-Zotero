import React, { useEffect, useState } from "react";
import { deskModel } from "../../api/search";
import { useSettings, type Settings } from "../../contexts/SettingsContext";
import ActiveModelPanel from "../models/ActiveModelPanel";
import type { DeskModel } from "../../types/desk";

type JobKey = "deskReadQuery" | "deskNotes" | "deskAlsoTry" | "deskThemes" | "deskClerkCloud";

const JOBS: { key: JobKey; label: string; hint: string }[] = [
  {
    key: "deskReadQuery",
    label: "Read limits from my query",
    hint: "Only when the desk's own reader leaves a phrase unread, such as “anything Woodcock has written”. A local 4B model adds about five seconds to those searches.",
  },
  {
    key: "deskNotes",
    label: "A note on each item",
    hint: "One sentence on what the passages cover, checked against them. Where a note fails the checks, the row keeps its extract.",
  },
  {
    key: "deskAlsoTry",
    label: "Also try",
    hint: "Next searches chosen from your own tags and titles. Without a model, the most common ones are shown.",
  },
  {
    key: "deskThemes",
    label: "Themes",
    hint: "Groups the list by what titles share, named from their words. Without a model, groups are named by a shared tag or word.",
  },
];

/** "4 of 5" from a measured job's counts, or "" when the register has no such numbers. */
function share(results: Record<string, unknown> | undefined, part: string): string {
  const n = results?.[part];
  const of = results?.cases;
  return typeof n === "number" && typeof of === "number" ? `${n} of ${of}` : "";
}

/**
 * The desk clerk: the optional model and the jobs it may do. The desk works
 * without it; every job has an answer that needs no model (backend/clerk.py).
 */
const ClerkRoom: React.FC = () => {
  const { settings, updateSettings, availableProviders } = useSettings();
  const provider = availableProviders.find((p) => p.id === settings.activeProviderId);
  const [info, setInfo] = useState<DeskModel | null>(null);
  const [saving, setSaving] = useState<JobKey | null>(null);

  useEffect(() => {
    deskModel().then(setInfo).catch(() => setInfo(null));
  }, [settings.activeProviderId, settings.activeModel, settings.providers]);

  async function toggle(key: JobKey, value: boolean) {
    setSaving(key);
    try {
      await updateSettings({ [key]: value } as Partial<Settings>);
    } finally {
      setSaving(null);
    }
  }

  const measured = info?.measured;
  const reading = share(measured?.results.read_query, "correct");
  const notes = share(measured?.results.note, "model_used");

  return (
    <div className="clerk-room">
      <div className="panel-head"><span className="panel-head__title">The desk clerk</span></div>
      <p className="clerk-room__intro">
        Optional. A language model can help at the desk: reading limits out of your query, writing a one-line note on
        each item, suggesting next searches and naming groups. It never answers your question, and every job falls back
        to the desk's own work when the model is missing, slow, or fails a check.
      </p>

      <div className="clerk-room__status" role="status">
        {!info ? (
          <span>Checking the model…</span>
        ) : info.cloud && !info.cloud_allowed ? (
          <span>
            <strong>{info.model.split("/").pop()}</strong> is a cloud model. The clerk uses it only if you allow it
            below; until then the desk reads queries itself and shows extracts.
          </span>
        ) : !info.available ? (
          <span>No model set up. The desk reads queries itself and shows extracts.</span>
        ) : measured ? (
          <span>
            <strong>{measured.label}</strong> · measured by the desk on {measured.measured}
            {measured.hardware ? ` (${measured.hardware})` : ""}
            {reading ? `: read ${reading} test queries right` : ""}
            {notes ? `, ${notes} notes passed the checks` : ""}.
          </span>
        ) : (
          <span>
            <strong>{info.model.split("/").pop()}</strong> · not measured by the desk. Its work is checked all the same,
            but more of it may fall back.
          </span>
        )}
      </div>
      {info?.cloud && provider && (
        <label className="clerk-job clerk-room__cloud">
          <input
            type="checkbox"
            checked={settings.deskClerkCloud === true}
            disabled={saving === "deskClerkCloud"}
            onChange={(e) => toggle("deskClerkCloud", e.target.checked).then(() => deskModel().then(setInfo).catch(() => undefined))}
          />
          <span className="clerk-job__text">
            <span className="clerk-job__label">Let the clerk use {provider.label}</span>
            <span className="clerk-job__hint clerk-room__privacy">
              {provider.label} is a cloud service: your queries, and up to three passages for each note, would be sent to it.
            </span>
          </span>
        </label>
      )}

      <ActiveModelPanel hint="the clerk's model and legacy chat's" />

      <fieldset className="clerk-room__jobs">
        <legend className="desk-label">Jobs</legend>
        {JOBS.map((job) => (
          <label key={job.key} className="clerk-job">
            <input
              type="checkbox"
              checked={settings[job.key] !== false}
              disabled={saving === job.key}
              onChange={(e) => toggle(job.key, e.target.checked)}
            />
            <span className="clerk-job__text">
              <span className="clerk-job__label">{job.label}</span>
              <span className="clerk-job__hint">{job.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
    </div>
  );
};

export default ClerkRoom;
