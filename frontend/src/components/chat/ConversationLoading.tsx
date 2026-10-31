import { AgentWorkingIndicator } from './AgentWorkingIndicator'

export function ConversationLoading({ label = '正在加载对话' }: { label?: string }) {
  return <div className="mx-auto w-full max-w-[680px] px-5 py-10 md:px-6">
    <AgentWorkingIndicator label={label} spacious />
    <div aria-hidden="true" className="mt-6 ml-[60px] space-y-3.5">
      <div className="h-2.5 w-2/5 animate-pulse rounded-full bg-ink/10"/>
      <div className="h-2.5 w-4/5 animate-pulse rounded-full bg-ink/5"/>
      <div className="h-2.5 w-3/5 animate-pulse rounded-full bg-ink/5"/>
    </div>
  </div>
}
