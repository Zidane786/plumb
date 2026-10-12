"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { Spinner } from "@/components/ui/spinner";

export function BookingForm() {
  const [status, setStatus] = useState<"idle" | "saving" | "error" | "success">("idle");
  if (status === "error") return <ErrorState message="We could not save the booking" />;
  if (status === "success") return <p>Booking confirmed</p>;
  return (
    <form onSubmit={() => setStatus("saving")}>
      <label htmlFor="guests">Guests</label>
      <input id="guests" name="guests" type="number" />
      <Button type="submit" disabled={status === "saving"}>
        {status === "saving" ? <Spinner /> : "Confirm booking"}
      </Button>
    </form>
  );
}
