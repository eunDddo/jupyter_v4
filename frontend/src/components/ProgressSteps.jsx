import React from 'react'

// Renders the live pipeline progress while waiting for an answer.
// steps: [{ node, label, detail }] in arrival order. The last step is treated
// as the one currently in progress; all earlier steps are marked complete.
export default function ProgressSteps({ steps }) {
  if (!steps || steps.length === 0) {
    return (
      <div className="progress-steps">
        <div className="progress-title">진행 단계</div>
        <div className="loading-row">
          <span className="spinner" /> 답변을 생성하는 중입니다… (수 초 소요)
        </div>
      </div>
    )
  }

  const lastIndex = steps.length - 1
  return (
    <div className="progress-steps">
      <div className="progress-title">진행 단계</div>
      <ul className="step-list">
        {steps.map((s, i) => {
          const active = i === lastIndex
          return (
            <li
              key={`${s.node}-${i}`}
              className={`step-item ${active ? 'active' : 'done'}`}
            >
              <span className="step-icon">
                {active ? <span className="spinner small-spinner" /> : '✓'}
              </span>
              <span className="step-body">
                <span className="step-label">{s.label || s.node}</span>
                {s.detail && <span className="step-detail">{s.detail}</span>}
                {active && <span className="step-status muted small">진행 중</span>}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
