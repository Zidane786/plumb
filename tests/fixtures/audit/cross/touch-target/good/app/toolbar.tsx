export const Toolbar = () => (
  <nav>
    <button className="h-11 w-11 rounded-md">x</button>
    <button className="size-8 pointer-coarse:size-11">y</button>
    <div className="h-8 w-8">not interactive</div>
    <button className="h-8 min-h-11 px-4">z</button>
    <a href="/help">Help</a>
  </nav>
);
