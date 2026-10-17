// expect: none
export function Layout() {
  return (
    <div className="w-[320px] h-[calc(100vh-4rem)] min-w-[12rem] top-[4px] left-[50%] grid-cols-[1fr_2fr] z-[60]">
      <p className="bg-[var(--color-primary)] text-(--color-on-surface) translate-x-[2px]">x</p>
    </div>
  );
}
