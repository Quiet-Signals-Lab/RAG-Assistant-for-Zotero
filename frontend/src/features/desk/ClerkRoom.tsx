import React, { useEffect, useState } from "react";
import { deskModel } from "../../api/search";
import { useSettings, type Settings } from "../../contexts/SettingsContext";
import ActiveModelPanel from "../models/ActiveModelPanel";
import type { DeskModel } from "../../types/desk";

type JobKey = "deskReadQuery" | "deskAlsoTry" | "deskThemes" | "deskClerkCloud";

const JOBS: { key: JobKey; label: string; hint: string }[] = [
  {
    key: "deskReadQuery",
    label: "Read limits from my query",
    hint: "Only when the app's own reader leaves a phrase unread, such as “anything Woodcock has written”. A local 4B model adds about five seconds to those searches.",
  },
  {
    key: "deskAlsoTry",
    label: "Suggested next searches",
    hint: "Chosen from your own tags and titles. Without a model, the most common ones are shown.",
  },
  {
    key: "deskThemes",
    label: "Named theme groups",
    hint: "Groups the results by what titles share, named from their words. Without a model, groups are named by a shared tag or word.",
  },
];

/** "4 of 5" from a measured job's counts, or "" when the register has no such numbers. */
function share(results: Record<string, unknown> | undefined, part: string): string {
  const n = results?.[part];
  const of = results?.cases;
  return typeof n === "number" && typeof of === "number" ? `${n} of ${of}` : "";
}

/**
 * The language model panel: the optional model and the jobs it may do. Search
 * works without it; every job has an answer that needs no model (backend/clerk.py).
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

  return (
    <div className="clerk-room">
      <div className="panel-head"><h2 className="panel-head__title">Language model</h2></div>
      <p className="clerk-room__intro">
        Optional. A language model can add to search results: it can read limits out of your query, suggest next
        searches and name groups. What it read from your query is shown under the search box. It never answers your
        question, and each job falls back to the app's own method when the model is missing, slow, or fails a check.
      </p>

      <div className="clerk-room__status" role="status">
        {!info ? (
          <span>Checking which model is set up…</span>
        ) : info.cloud && !info.cloud_allowed ? (
          <span>
            <strong>{info.model.split("/").pop()}</strong> is a cloud model. It is used only if you allow it below;
            until then the app reads queries itself.
          </span>
        ) : !info.available ? (
          <span>No model set up. The app reads queries itself.</span>
        ) : measured ? (
          <span>
            <strong>{measured.label}</strong> · measured for these jobs on {measured.measured}
            {measured.hardware ? ` (${measured.hardware})` : ""}
            {reading ? `: read ${reading} test queries right` : ""}.
          </span>
        ) : (
          <span>
            <strong>{info.model.split("/").pop()}</strong> · not measured for these jobs. Its work is checked all the
            same, but more of it may fall back.
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
            <span className="clerk-job__label">Allow {provider.label} for these jobs</span>
            <span className="clerk-job__hint clerk-room__privacy">
              {provider.label} is a cloud service: your queries, and the titles and tags of your results, would be sent to it.
            </span>
          </span>
        </label>
      )}

      <ActiveModelPanel hint="the model for these jobs and for legacy chat" />

      <fieldset className="clerk-room__jobs">
        <legend className="desk-label">What the model may do</legend>
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
