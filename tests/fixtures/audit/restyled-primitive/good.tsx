// expect: none
import { Button } from "@/components/ui/button";
export function Save({ go }: { go: () => void }) {
  return (
    <Button variant="ghost" onClick={() => go()} className="w-full text-center mt-2">
      Save
    </Button>
  );
}
