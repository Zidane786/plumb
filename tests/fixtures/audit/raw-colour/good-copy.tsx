// expect: none
export function Order({ n }: { n: number }) {
  const label = "Ticket #789";
  return <p title="Issue #456">Order #123 and #1234 {label}</p>;
}
