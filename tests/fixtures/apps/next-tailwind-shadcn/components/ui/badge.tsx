export function Badge({ label }: { label: string }) {
  return (
    <span className="rounded-md border border-border bg-secondary px-2 text-xs text-secondary-foreground">
      {label}
    </span>
  );
}

export function SidebarItem({ label }: { label: string }) {
  return (
    <a className="rounded-xl bg-sidebar-accent p-2 text-sidebar-accent-foreground hover:bg-muted hover:text-muted-foreground">
      {label}
    </a>
  );
}
