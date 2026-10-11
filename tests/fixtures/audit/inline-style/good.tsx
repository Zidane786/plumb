// expect: none
export function Pin({ x }: { x: number }) {
  return <div style={{ width: 320, top: 4, left: x, gridTemplateColumns: "1fr 2fr" }} data-style="color: x" />;
}
