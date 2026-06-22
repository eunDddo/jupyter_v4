import React, { useCallback, useEffect, useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import UsageTab from './components/UsageTab.jsx'
import { api, ApiError } from './api.js'

const USER_KEY = 'ma_user_id'

function describeError(err) {
  if (err instanceof ApiError) {
    if (err.status === 0) return '서버에 연결할 수 없습니다.'
    if (err.status === 404) return '사용자/대화를 찾을 수 없습니다.'
  }
  return '오류가 발생했습니다. 잠시 후 다시 시도하세요.'
}

export default function App() {
  const [userId, setUserId] = useState(() => localStorage.getItem(USER_KEY) || '')
  const [threads, setThreads] = useState([])
  const [selectedThreadId, setSelectedThreadId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('chat')

  const refreshThreads = useCallback(async (uid) => {
    if (!uid) {
      setThreads([])
      return
    }
    try {
      const res = await api.listThreads(uid)
      setThreads(res?.threads || [])
    } catch (err) {
      // If the stored user no longer exists, clear it.
      if (err instanceof ApiError && err.status === 404) {
        localStorage.removeItem(USER_KEY)
        setUserId('')
        setThreads([])
      }
      setError(describeError(err))
    }
  }, [])

  useEffect(() => {
    refreshThreads(userId)
  }, [userId, refreshThreads])

  const handleCreateUser = async () => {
    setBusy(true)
    setError('')
    try {
      const res = await api.createUser()
      localStorage.setItem(USER_KEY, res.user_id)
      setUserId(res.user_id)
      setSelectedThreadId('')
      setThreads([])
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDeleteUser = async () => {
    if (!userId) return
    if (!window.confirm('현재 사용자를 삭제하시겠습니까? 모든 대화가 사라집니다.')) return
    setBusy(true)
    setError('')
    try {
      await api.deleteUser(userId)
    } catch (err) {
      setError(describeError(err))
    } finally {
      localStorage.removeItem(USER_KEY)
      setUserId('')
      setThreads([])
      setSelectedThreadId('')
      setBusy(false)
    }
  }

  const handleCreateThread = async () => {
    if (!userId) return
    setBusy(true)
    setError('')
    try {
      const res = await api.createThread(userId)
      await refreshThreads(userId)
      setSelectedThreadId(res.thread_id)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDeleteThread = async (threadId) => {
    if (!userId) return
    if (!window.confirm('이 대화를 삭제하시겠습니까?')) return
    setBusy(true)
    setError('')
    try {
      await api.deleteThread(userId, threadId)
      if (threadId === selectedThreadId) setSelectedThreadId('')
      await refreshThreads(userId)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <Sidebar
        userId={userId}
        threads={threads}
        selectedThreadId={selectedThreadId}
        busy={busy}
        onCreateUser={handleCreateUser}
        onDeleteUser={handleDeleteUser}
        onCreateThread={handleCreateThread}
        onSelectThread={setSelectedThreadId}
        onDeleteThread={handleDeleteThread}
      />
      <div className="main-area">
        <nav className="tab-bar">
          <button
            className={`tab ${tab === 'chat' ? 'active' : ''}`}
            onClick={() => setTab('chat')}
          >
            대화
          </button>
          <button
            className={`tab ${tab === 'usage' ? 'active' : ''}`}
            onClick={() => setTab('usage')}
          >
            사용량
          </button>
        </nav>
        {error && <div className="global-error">{error}</div>}
        {tab === 'chat' ? (
          <ChatPanel
            key={`${userId}:${selectedThreadId}`}
            userId={userId}
            threadId={selectedThreadId}
          />
        ) : (
          <UsageTab />
        )}
      </div>
    </div>
  )
}
