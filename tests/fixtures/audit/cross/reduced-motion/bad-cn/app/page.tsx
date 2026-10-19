import { cn } from "../lib/cn";
const note = "A smooth transition";
export const P = ({ open }) => (
  <div className={cn("rounded-md", open && "transition-opacity")}>{note}</div>
);
