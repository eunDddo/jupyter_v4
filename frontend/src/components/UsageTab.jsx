import React, { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api.js'

function fmtNum(n) {
  if (n === undefined || n === null) return '0'
  return Number(n).toLocaleString('en-US')
}

function fmtUsd(n) {
  const v = Number(n || 0)
  return `$${v.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  })}`
}

function errorMessage(err) {
  if (err instanceof ApiError) {
    if (err.status === 0) return '서버에 연결할 수 없습니다.'
    if (err.status === 404) return '사용량 정보를 찾을 수 없습니다.'
  }
  return '사용량을 불러오지 못했습니다. 잠시 후 다시 시도하세요.'
}

export default function UsageTab() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.getUsage()
      setData(res)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const totals = data?.totals || {}
  const byModel = data?.by_model || {}
  const models = Object.keys(byModel)

  return (
    <div className="usage-tab">
      <div className="usage-header">
        <h2 className="usage-h2">사용량 (OpenTelemetry)</h2>
        <button className="btn btn-refresh" onClick={load} disabled={loading}>
          {loading ? '불러오는 중…' : '새로고침'}
        </button>
      </div>

      {error && <div className="error-line usage-error">{error}</div>}

      {!data && loading && (
        <div className="loading-row">
          <span className="spinner" /> 사용량을 불러오는 중…
        </div>
      )}

      {data && (
        <>
          <div className="usage-cards">
            <div className="usage-card">
              <div className="card-label">총 호출수</div>
              <div className="card-value">{fmtNum(totals.calls)}</div>
            </div>
            <div className="usage-card">
              <div className="card-label">총 토큰</div>
              <div className="card-value">{fmtNum(totals.total_tokens)}</div>
              <div className="card-sub muted small">
                입력 {fmtNum(totals.input_tokens)} · 출력{' '}
                {fmtNum(totals.output_tokens)}
              </div>
            </div>
            <div className="usage-card">
              <div className="card-label">추정 비용</div>
              <div className="card-value">{fmtUsd(totals.est_cost_usd)}</div>
            </div>
            <div className="usage-card">
              <div className="card-label">오류</div>
              <div className="card-value">{fmtNum(totals.errors)}</div>
            </div>
          </div>

          <div className="usage-section">
            <div className="section-label">모델별</div>
            <div className="usage-table-wrap">
              <table className="usage-table">
                <thead>
                  <tr>
                    <th>model</th>
                    <th className="num">calls</th>
                    <th className="num">input_tokens</th>
                    <th className="num">output_tokens</th>
                    <th className="num">total_tokens</th>
                    <th className="num">est_cost_usd</th>
                  </tr>
                </thead>
                <tbody>
                  {models.length === 0 && (
                    <tr>
                      <td colSpan={6} className="muted">
                        데이터가 없습니다.
                      </td>
                    </tr>
                  )}
                  {models.map((m) => {
                    const r = byModel[m] || {}
                    return (
                      <tr key={m}>
                        <td className="model-cell">{m}</td>
                        <td className="num">{fmtNum(r.calls)}</td>
                        <td className="num">{fmtNum(r.input_tokens)}</td>
                        <td className="num">{fmtNum(r.output_tokens)}</td>
                        <td className="num">{fmtNum(r.total_tokens)}</td>
                        <td className="num">{fmtUsd(r.est_cost_usd)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {data.note && <div className="usage-note muted small">{data.note}</div>}
        </>
      )}
    </div>
  )
}
