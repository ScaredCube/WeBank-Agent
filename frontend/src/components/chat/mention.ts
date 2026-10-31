/** Locate an @ reference query at the text caret without changing other text. */
export function findMention(value: string, caret: number): {start:number,end:number,query:string}|null {
  const before = value.slice(0, Math.max(0, Math.min(caret, value.length)))
  const match = /@([^@\s\n]{0,24})$/.exec(before)
  if (!match) return null
  return {start: before.length - match[0].length, end:before.length, query:match[1]}
}
