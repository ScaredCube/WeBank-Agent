export type WorkspacePanelName = 'assets' | 'activity' | 'collections'

export function initialWorkspacePanel(): WorkspacePanelName | null {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null
  return null
}
