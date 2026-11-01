import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { lazy, Suspense } from 'react'

import { RequireAuth } from '@/components/RequireAuth'
import { PageErrorBoundary } from '@/components/PageErrorBoundary'
import { LoginPage } from '@/pages/Login'
import { AuthProvider } from '@/lib/auth'
import { ThemeProvider } from '@/features/theme/ThemeProvider'

const ChatPage = lazy(() => import('@/pages/Chat').then(({ ChatPage }) => ({ default: ChatPage })))

export default function App() {
  return (
    <ThemeProvider><Routes>
      <Route element={<AuthProvider><Outlet /></AuthProvider>}>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/chat"
          element={
            <RequireAuth>
              <PageErrorBoundary><Suspense fallback={<div role="status" className="grid min-h-dvh place-items-center bg-canvas text-sm text-muted">正在加载对话…</div>}><ChatPage /></Suspense></PageErrorBoundary>
            </RequireAuth>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes></ThemeProvider>
  )
}
