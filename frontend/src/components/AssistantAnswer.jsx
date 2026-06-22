import React, { useState } from 'react'

// Renders an assistant response: the plain-text answer (pre-wrap), citations,
// warnings (collapsible), and an optional debug trace box.
export default function AssistantAnswer({ data }) {
  const [warnOpen, setWarnOpen] = useState(false)
  const {
    answer,
    citations = [],
    warnings = [],
    missing_inputs = [],
    blocked,
    trace,
  } = data || {}

  return (
    <div className={`assistant-answer ${blocked ? 'blocked' : ''}`}>
      {blocked && <div className="notice-tag">⚠ 차단된 응답 (blocked)</div>}

      <div className="answer-text">{answer}</div>

      {missing_inputs.length > 0 && (
        <div className="missing-inputs">
          <span className="section-label">추가 입력이 필요합니다:</span>{' '}
          {missing_inputs.join(', ')}
        </div>
      )}

      {citations.length > 0 && (
        <div className="citations">
          <div className="section-label">출처</div>
          <ul>
            {citations.map((c, i) => (
              <li key={c.citation_id ?? i}>
                <span className="cite-title">{c.title || c.citation_id}</span>
                {c.source && <span className="cite-source"> — {c.source}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="warnings">
          <button
            type="button"
            className="collapse-toggle muted"
            onClick={() => setWarnOpen((o) => !o)}
          >
            {warnOpen ? '▼' : '▶'} 경고 {warnings.length}건
          </button>
          {warnOpen && (
            <ul className="muted small">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {trace && (
        <div className="trace-box">
          <div className="section-label">debug trace</div>
          {Array.isArray(trace.gates) && trace.gates.length > 0 && (
            <pre>
              gates:
              {'\n'}
              {trace.gates
                .map(([name, status]) => `  ${name}: ${status}`)
                .join('\n')}
            </pre>
          )}
          {Array.isArray(trace.tasks) && trace.tasks.length > 0 && (
            <pre>
              tasks:
              {'\n'}
              {trace.tasks.map((t) => `  - ${t}`).join('\n')}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
