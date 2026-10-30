export function ConversationLoading({ label = '正在加载对话' }: { label?: string }) {
  return <div className="mx-auto w-full max-w-[760px] px-5 py-10" role="status">
    <span className="sr-only">{label}</span>
    <div className="h-4 w-2/5 rounded bg-ink/10" />
    <div className="mt-4 h-4 w-4/5 rounded bg-ink/5" />
  </div>
}
