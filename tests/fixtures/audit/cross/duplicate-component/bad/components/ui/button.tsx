import * as React from "react";
export function Button(props: React.ComponentProps<"button">) {
  return <button className="bg-primary text-on-primary rounded-md px-4 py-2 focus-visible:ring-2" {...props} />;
}
