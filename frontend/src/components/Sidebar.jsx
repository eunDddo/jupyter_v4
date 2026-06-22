import React from 'react'

function truncate(id) {
  if (!id) return ''
  return id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id
}

export default function Sidebar({
  userId,
  threads,
  selectedThreadId,
  busy,
  onCreateUser,
  onDeleteUser,
  onCreateThread,
  onSelectThread,
  onDeleteThread,
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-section">
        <h1 className="app-title">제조 설비 진단</h1>
        <div className="muted small">어시스턴트</div>
      </div>

      <div className="sidebar-section">
        <div className="section-label">현재 사용자</div>
        {userId ? (
          <div className="user-id" title={userId}>{truncate(userId)}</div>
        ) : (
          <div className="muted small">사용자가 없습니다</div>
        )}
        <div className="btn-row">
          <button className="btn" onClick={onCreateUser} disabled={busy}>
            새 사용자 생성
          </button>
          <button
            className="btn btn-danger"
            onClick={onDeleteUser}
            disabled={busy || !userId}
          >
            사용자 삭제
          </button>
        </div>
      </div>

      <div className="sidebar-section threads">
        <div className="section-label">대화 목록</div>
        <button
          className="btn btn-full"
          onClick={onCreateThread}
          disabled={busy || !userId}
        >
          + 새 대화(thread) 생성
        </button>
        <ul className="thread-list">
          {threads.length === 0 && userId && (
            <li className="muted small empty">대화가 없습니다</li>
          )}
          {threads.map((t) => (
            <li
              key={t.thread_id}
              className={`thread-item ${
                t.thread_id === selectedThreadId ? 'active' : ''
              }`}
              onClick={() => onSelectThread(t.thread_id)}
            >
              <span className="thread-title">
                {t.title || `대화 ${t.thread_id.slice(0, 6)}`}
              </span>
              <button
                className="icon-btn"
                title="대화 삭제"
                onClick={(e) => {
                  e.stopPropagation()
                  onDeleteThread(t.thread_id)
                }}
              >
                🗑
              </button>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  )
}
