export const Row = () => (
  <li className="group flex">
    <button className="opacity-0 group-hover:opacity-100 group-focus-within:opacity-100">Edit</button>
    <button className="invisible group-hover:visible focus-visible:visible">Delete</button>
    <span className="opacity-0 transition-opacity">x</span>
    <a className="hover:opacity-80" href="/a">A</a>
  </li>
);
