// expect: restyled-primitive@4
import { Button } from "@/components/ui/button";
export function Save({ go }: { go: () => void }) {
  return <Button onClick={() => go()} className={cn("w-full", "rounded-md")}>Save</Button>;
}
