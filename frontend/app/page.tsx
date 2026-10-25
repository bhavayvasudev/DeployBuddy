"use client";

import { useState } from "react";

type Settings = {
  repository_url: string;
  service_name: string;
  build_command: "npm ci" | "npm ci && npm run build";
  start_command: "npm start";
  runtime: "node";
  service_type: "web";
  provider: "render";
  mode: "dry_run";
};
type Operation = { sequence: number; kind: string; description: string; settings: Settings };
type Preview = { plan_digest: string; settings: Settings; operations: Operation[]; notice: string };
type Status = {
  id: string;
  status: string;
  mode: string;
  confirmed_at: string;
  created_at: string;
  plan_digest: string;
  operations: Operation[];
  events: { id: number; from_status: string | null; to_status: string; message: string; created_at: string }[];
};
const initialSettings: Settings = {
  repository_url: "",
  service_name: "",
  build_command: "npm ci && npm run build",
  start_command: "npm start",
  runtime: "node",
  service_type: "web",
  provider: "render",
  mode: "dry_run",
};

async function api<T>(path: string, body?: object): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/requests${path}`, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw new Error("The local API could not be reached. Start the backend, then retry.");
  }
  if (!response.ok) {
    const messages: Record<number, string> = {
      404: "Dry-run request not found.",
      409: "The proposal or submission key conflicts. Review the settings and preview again.",
      422: "Check the GitHub URL and supported service settings, then preview again.",
      503: "The local database is unavailable. Check the database and migrations, then retry.",
    };
    throw new Error(messages[response.status] ?? "The local API returned an error. Please retry.");
  }
  return response.json() as Promise<T>;
}

function OperationSummary({ operation }: { operation: Operation }) {
  const settings = operation.settings;
  return (
    <div className="operation">
      <p><strong>{operation.sequence}. {operation.description}</strong></p>
      <dl>
        <dt>Repository</dt><dd>{settings.repository_url}</dd>
        <dt>Service</dt><dd>{settings.service_name}</dd>
        <dt>Configuration</dt><dd>One Node.js web service · Render · dry_run</dd>
        <dt>Build command</dt><dd><code>{settings.build_command}</code></dd>
        <dt>Start command</dt><dd><code>{settings.start_command}</code></dd>
      </dl>
    </div>
  );
}

export default function Home() {
  const [settings, setSettings] = useState<Settings>(initialSettings);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [submissionKey, setSubmissionKey] = useState<string | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [requestId, setRequestId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function edit(patch: Partial<Settings>) {
    setSettings({ ...settings, ...patch });
    setPreview(null);
    setConfirmed(false);
    setSubmissionKey(null);
    setError("");
  }

  async function review(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setPreview(null);
    setConfirmed(false);
    try {
      setPreview(await api<Preview>("/preview", settings));
      setSubmissionKey(crypto.randomUUID());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Preview failed.");
    } finally { setBusy(false); }
  }

  async function submit() {
    if (!preview || !confirmed || !submissionKey || busy) return;
    setBusy(true);
    setError("");
    try {
      const saved = await api<Status>("", {
        ...preview.settings,
        confirmed: true,
        plan_digest: preview.plan_digest,
        idempotency_key: submissionKey,
      });
      setStatus(saved);
      setRequestId(saved.id);
      setConfirmed(false);
      try { localStorage.setItem("deploy-buddy-last-request", saved.id); } catch { /* Optional. */ }
    } catch (cause) {
      // Preserve the proposal and key for safe retries after an ambiguous response.
      setError(cause instanceof Error ? cause.message : "Save failed. Retry the same proposal.");
    } finally { setBusy(false); }
  }

  async function refresh(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await loadRequest(requestId.trim());
  }

  async function loadRequest(id: string) {
    setRequestId(id);
    setBusy(true);
    setError("");
    setStatus(null);
    try {
      setStatus(await api<Status>(`/${encodeURIComponent(id)}`));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Status lookup failed.");
    } finally { setBusy(false); }
  }

  async function loadLastSaved() {
    try {
      const id = localStorage.getItem("deploy-buddy-last-request");
      if (id) await loadRequest(id);
      else setError("No request has been saved in this browser yet. Paste a request ID to load it.");
    } catch {
      setError("Browser storage is unavailable. Paste a request ID to load it.");
    }
  }

  return (
    <main>
      <p className="eyebrow">Deploy Buddy / Local development</p>
      <h1>Review a deployment.<br />Save the plan.</h1>
      <p className="intro">Validate a GitHub repository URL and plan one Node.js web service.</p>
      <p className="notice">Dry-run only. No commands run, no external services are contacted, and no external resources are created.</p>
      <section aria-labelledby="settings-title">
        <span className="badge">Milestone 2 · Dry-run</span>
        <h2 id="settings-title">1. Configure the service</h2>
        <p>Use a public GitHub HTTPS URL. Visibility, existence and repository contents are not checked offline. No credentials or environment variables are accepted.</p>
        <form onSubmit={review}>
          <fieldset disabled={busy}>
            <label htmlFor="repository">GitHub repository URL</label>
            <input id="repository" type="url" required maxLength={512} placeholder="https://github.com/owner/repository" value={settings.repository_url} onChange={(e) => edit({ repository_url: e.target.value })} />
            <label htmlFor="service">Service name</label>
            <input id="service" required maxLength={63} pattern="[a-z]([a-z0-9-]*[a-z0-9])?" placeholder="my-node-service" value={settings.service_name} onChange={(e) => edit({ service_name: e.target.value })} />
            <label htmlFor="build">Build command</label>
            <select id="build" value={settings.build_command} onChange={(e) => edit({ build_command: e.target.value as Settings["build_command"] })}>
              <option value="npm ci && npm run build">npm ci &amp;&amp; npm run build</option>
              <option value="npm ci">npm ci</option>
            </select>
            <p>Start command: <code>npm start</code> · Runtime: Node.js · Service type: web · Planned provider: Render</p>
            <button type="submit">Preview dry-run</button>
          </fieldset>
        </form>
      </section>
      {preview && <section aria-labelledby="preview-title">
        <h2 id="preview-title">2. Review and explicitly confirm</h2>
        {preview.operations.map((operation) => <OperationSummary key={operation.sequence} operation={operation} />)}
        <p className="notice">{preview.notice}</p>
        <p className="digest">Proposal: <code>{preview.plan_digest}</code></p>
        <label className="confirmation"><input type="checkbox" checked={confirmed} disabled={busy} onChange={(e) => setConfirmed(e.target.checked)} />I explicitly confirm saving this exact dry-run plan locally. No deployment will be executed.</label>
        <button type="button" disabled={!confirmed || busy} onClick={submit}>Save confirmed dry-run</button>
        <p className="footnote">Editing settings requires a fresh preview and confirmation. Retrying this proposal reuses the submission key.</p>
      </section>}
      <section aria-labelledby="status-title">
        <h2 id="status-title">3. Request status</h2>
        <form onSubmit={refresh}>
          <label htmlFor="request-id">Request ID</label>
          <input id="request-id" required value={requestId} disabled={busy} onChange={(e) => setRequestId(e.target.value)} placeholder="Paste a saved request UUID" />
          <button type="submit" disabled={busy || !requestId.trim()}>Load request status</button>
          {" "}<button type="button" disabled={busy} onClick={loadLastSaved}>Load last saved request</button>
        </form>
        {status && <div className="saved" aria-live="polite">
          <h3>Saved request: <span className="badge">{status.status}</span></h3>
          <p className="digest">Request ID: <code>{status.id}</code></p>
          <p>Mode: <strong>{status.mode}</strong> · Confirmed: {new Date(status.confirmed_at).toLocaleString()}</p>
          {status.operations.map((operation) => <OperationSummary key={operation.sequence} operation={operation} />)}
          <h3>Audit events</h3>
          <ol>{status.events.map((event) => <li key={event.id}><strong>{event.from_status ?? "new"} → {event.to_status}</strong><p>{event.message}</p><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time></li>)}</ol>
          <p className="notice">Planning is complete. This request will remain planned; execution is unavailable.</p>
        </div>}
      </section>
      {busy && <p role="status">Contacting the local API…</p>}
      {error && <p role="alert" className="error">{error}</p>}
    </main>
  );
}
