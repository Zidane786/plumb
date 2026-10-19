import { Button } from "../components/ui/button";
export const Page = () => (
  <main>
    <Button>Go</Button>
    <button className="bg-surface rounded-sm px-4 py-2 text-on-surface">Plain</button>
    <button className="underline">Link-like</button>
  </main>
);
