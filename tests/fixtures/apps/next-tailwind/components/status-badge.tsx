export function StatusBadge({ label }: { label: string }) {
  return (
    <span className="outline-none transition-colors duration-[250ms]" style={{ color: "#c0392b" }}>
      {label}
    </span>
  );
}
