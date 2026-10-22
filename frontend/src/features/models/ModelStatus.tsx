import React, { useEffect, useState } from "react";
import { apiFetch } from "../../api/client";
import { useSettings } from "../../contexts/SettingsContext";
import { useDesk } from "../desk/DeskContext";

type Check = { ok: boolean | null; detail: string };

/**
 * The active model and whether it can be reached, in the header. A local
 * provider must be running and list the model; a cloud provider must accept
 * its key. Checked on load, when the model settings change, and once a minute.
 */
const ModelStatus: React.FC = () => {
  const { settings, availableProviders } = useSettings();
  const desk = useDesk();
  const providerId = settings.activeProviderId;
  const model = settings.activeModel;
  const provider = availableProviders.find((p) => p.id === providerId);
  const local = !!provider && !provider.requires_api_key;
  const [check, setCheck] = useState<Check>({ ok: null, detail: "" });

  useEffect(() => {
    if (!providerId || !model) {
      setCheck({ ok: null, detail: "" });
      return;
    }
    let cancelled = false;
    const run = async () => {
      let next: Check;
      try {
        const r = await apiFetch(`/api/providers/${providerId}/validate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        const d = await r.json();
        next = { ok: !!d.valid, detail: d.valid ? "" : d.error || d.message || d.details || "Not reachable" };
        if (next.ok && local) {
          const ids: string[] = ((await (await apiFetch(`/api/providers/${providerId}/models`)).json()).models ?? []).map((m: { id: string }) => m.id);
          const base = (id: string) => id.split(":")[0];
          if (ids.length && !ids.some((id) => id === model || base(id) === base(model))) next = { ok: false, detail: `${model} is not loaded` };
        }
      } catch {
        next = { ok: false, detail: "Could not reach the backend" };
      }
      if (!cancelled) setCheck(next);
    };
    run();
    const timer = window.setInterval(run, 60000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [providerId, model, local, settings.providers]);

  const name = model ? model.split("/").pop() : "";
  const label = !providerId || !model ? "No model selected" : `${name} selected${local && check.ok === false ? " (Not running)" : ""}`;
  const dot = check.ok === true ? "model-status__dot model-status__dot--ok" : check.ok === false ? "model-status__dot model-status__dot--down" : "model-status__dot";
  const title = check.ok === true ? "Connected" : check.detail || "Choose a model in the Language model section";

  return (
    <button type="button" className="model-status" title={title} onClick={() => { desk.setRoom("clerk"); desk.setPane("ask"); }}>
      <span className={dot} aria-hidden="true" />
      <span className="model-status__label">{label}</span>
      <span className="sr-only">{check.ok === true ? ", connected" : check.ok === false ? ", not connected" : ""}</span>
    </button>
  );
};

export default ModelStatus;
