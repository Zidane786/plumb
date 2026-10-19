// expect: inline-style@3
export function Bar({ w }: { w: number }) {
  return <div style={{ width: `${w}px`, color: "var(--color-primary)" }} />;
}
