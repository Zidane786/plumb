// expect: hand-rolled-primitive@3
export function Row({ open }: { open: () => void }) {
  return <div className="p-4" onClick={() => open()}>Open</div>;
}
