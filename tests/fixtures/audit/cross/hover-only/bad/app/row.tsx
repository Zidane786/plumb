export const Row = () => (
  <li className="group flex">
    <button className="opacity-0 group-hover:opacity-100">Edit</button>
    <button className="invisible group-hover:visible">Delete</button>
    <button className="opacity-0 group-hover:opacity-100 focus:ring-2">Share</button>
  </li>
);
