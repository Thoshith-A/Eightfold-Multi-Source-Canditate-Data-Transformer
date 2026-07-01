import React, { useEffect, useMemo, useState } from "react";

// The projected output shape varies by config (full schema vs. renamed/subset),
// so the renderer adapts to the *shape* of each value rather than assuming the
// canonical schema. Confidence is shown as a bar; provenance as a table; fields
// the optional LLM lane filled get an "LLM" badge.

const API = "/api";

function ConfidenceBar({ value }) {
  const pct = Math.round((Number(value) || 0) * 100);
  const hue = Math.round(120 * (Number(value) || 0)); // red→green
  return (
    <div className="confbar" title={`confidence ${pct}%`}>
      <div className="confbar-fill" style={{ width: `${pct}%`, background: `hsl(${hue} 70% 45%)` }} />
      <span className="confbar-label">{pct}%</span>
    </div>
  );
}

function Chips({ items }) {
  return (
    <div className="chips">
      {items.map((it, i) => (
        <span className="chip" key={i}>{String(it)}</span>
      ))}
    </div>
  );
}

const isSkillArray = (v) =>
  Array.isArray(v) && v.length > 0 && v.every((x) => x && typeof x === "object" && "name" in x && "confidence" in x);
const isObjArray = (v) => Array.isArray(v) && v.length > 0 && v.every((x) => x && typeof x === "object");
const isStrArray = (v) => Array.isArray(v) && v.every((x) => typeof x === "string");

function SkillList({ skills }) {
  return (
    <div className="skills">
      {skills.map((s, i) => (
        <div className="skill" key={i}>
          <div className="skill-head">
            <span className="skill-name">{s.name}</span>
            <ConfidenceBar value={s.confidence} />
          </div>
          {Array.isArray(s.sources) && <div className="sources">{s.sources.map((src, j) => (
            <span className="src" key={j}>{src}</span>
          ))}</div>}
        </div>
      ))}
    </div>
  );
}

function ExperienceList({ items, llm }) {
  return (
    <div className="exp-list">
      {items.map((e, i) => (
        <div className="exp" key={i}>
          <div className="exp-top">
            <strong>{e.title || "—"}</strong>
            <span className="exp-co">{e.company || ""}</span>
            <span className="exp-dates">{[e.start, e.end || (e.start ? "present" : "")].filter(Boolean).join(" – ")}</span>
          </div>
          {e.summary && (
            <div className="exp-summary">
              {e.summary}
              {llm.has("experience.summary") && <span className="badge-llm">LLM</span>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function EducationList({ items }) {
  return (
    <div className="edu-list">
      {items.map((e, i) => (
        <div className="edu" key={i}>
          <strong>{e.degree || "—"}</strong>{e.field ? `, ${e.field}` : ""} — {e.institution || ""}
          {e.end_year ? <span className="edu-year"> ({e.end_year})</span> : null}
        </div>
      ))}
    </div>
  );
}

function KeyVals({ obj }) {
  return (
    <table className="kv">
      <tbody>
        {Object.entries(obj).map(([k, v]) => (
          <tr key={k}>
            <td className="kv-k">{k}</td>
            <td className="kv-v">{v === null || v === "" ? <em className="muted">null</em> : Array.isArray(v) ? v.join(", ") : String(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function prettyLabel(key) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function FieldBlock({ fieldKey, value, llm }) {
  const label = prettyLabel(fieldKey);
  const isLlm = llm.has(fieldKey);
  let body;
  if (isSkillArray(value)) body = <SkillList skills={value} />;
  else if (fieldKey === "experience" && isObjArray(value)) body = <ExperienceList items={value} llm={llm} />;
  else if (fieldKey === "education" && isObjArray(value)) body = <EducationList items={value} />;
  else if (isStrArray(value)) body = value.length ? <Chips items={value} /> : <em className="muted">none</em>;
  else if (isObjArray(value)) body = value.map((o, i) => <KeyVals key={i} obj={o} />);
  else if (value && typeof value === "object") body = <KeyVals obj={value} />;
  else if (value === null || value === "") body = <em className="muted">null</em>;
  else body = <span>{String(value)}</span>;

  return (
    <section className="field">
      <h4>{label}{isLlm && <span className="badge-llm">LLM</span>}</h4>
      {body}
    </section>
  );
}

function ProvenanceTable({ rows }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="field">
      <h4 className="prov-toggle" onClick={() => setOpen(!open)}>
        Provenance ({rows.length}) {open ? "▾" : "▸"}
      </h4>
      {open && (
        <table className="prov">
          <thead><tr><th>field</th><th>source</th><th>method</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td>{r.field}</td>
                <td>{r.source}</td>
                <td className={r.method === "merge_winner" ? "m-win" : r.method === "llm_extraction" ? "m-llm" : ""}>{r.method}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function CandidateCard({ data, llmFields }) {
  const llm = useMemo(() => new Set(llmFields), [llmFields]);
  const { full_name, candidate_id, overall_confidence, provenance, ...rest } = data;
  return (
    <article className="card">
      <header className="card-head">
        <div>
          <h2>{full_name || candidate_id || "Candidate"}</h2>
          {candidate_id && <span className="cid">{candidate_id}</span>}
        </div>
        {overall_confidence !== undefined && (
          <div className="overall">
            <span>overall confidence</span>
            <ConfidenceBar value={overall_confidence} />
          </div>
        )}
      </header>
      <div className="card-body">
        {Object.entries(rest).map(([k, v]) => (
          <FieldBlock key={k} fieldKey={k} value={v} llm={llm} />
        ))}
        {Array.isArray(provenance) && provenance.length > 0 && <ProvenanceTable rows={provenance} />}
      </div>
    </article>
  );
}

export default function App() {
  const [configs, setConfigs] = useState([]);
  const [config, setConfig] = useState("default");
  const [enrich, setEnrich] = useState(false);
  const [files, setFiles] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API}/configs`)
      .then((r) => r.json())
      .then((d) => setConfigs(d.configs || []))
      .catch(() => setConfigs([{ name: "default" }]));
  }, []);

  const llmFields = useMemo(
    () => (result?.enrichment_report || []).map((r) => r.field),
    [result]
  );

  async function send(url, withFiles) {
    setLoading(true); setError(""); setResult(null);
    try {
      const form = new FormData();
      form.append("config", config);
      form.append("enrich", String(enrich));
      if (withFiles) files.forEach((f) => form.append("files", f));
      const resp = await fetch(url, { method: "POST", body: form });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "request failed");
      setResult(data);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>Multi-Source Candidate Data Transformer</h1>
        <p className="sub">Deterministic core · provenance &amp; confidence · runtime output projection</p>
      </header>

      <div className="controls">
        <label className="ctl">
          <span>Output config</span>
          <select value={config} onChange={(e) => setConfig(e.target.value)}>
            {configs.map((c) => (
              <option key={c.name} value={c.name}>{c.name}</option>
            ))}
          </select>
        </label>

        <label className="ctl">
          <span>Sources</span>
          <input type="file" multiple onChange={(e) => setFiles(Array.from(e.target.files))} />
        </label>

        <label className="ctl checkbox">
          <input type="checkbox" checked={enrich} onChange={(e) => setEnrich(e.target.checked)} />
          <span>Enrich (optional LLM gap-fill)</span>
        </label>

        <div className="buttons">
          <button disabled={loading || files.length === 0} onClick={() => send(`${API}/transform`, true)}>
            Transform uploaded
          </button>
          <button className="secondary" disabled={loading} onClick={() => send(`${API}/transform/samples`, false)}>
            Run bundled sample
          </button>
        </div>
      </div>

      {loading && <div className="status">Transforming…</div>}
      {error && <div className="status error">⚠ {error}</div>}

      {result && (
        <div className="results">
          <div className="meta">
            {result.count} candidate(s){result.enriched ? " · enriched" : ""}
            {result.enriched && result.enrichment_report?.length > 0 && (
              <span className="meta-llm"> · {result.enrichment_report.length} LLM gap-fill(s) @ conf 0.4</span>
            )}
          </div>
          {result.enrichment_status && (
            <div className={result.enriched ? "notice ok" : "notice warn"}>
              {result.enriched ? "✓ " : "⚠ "}{result.enrichment_status}
            </div>
          )}
          {result.candidates.map((c, i) => (
            <CandidateCard key={i} data={c} llmFields={llmFields} />
          ))}
        </div>
      )}
    </div>
  );
}
