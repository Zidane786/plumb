import { EmptyState } from "@/components/empty-state";
import { TableList } from "@/components/table-list";
import { useTables } from "@/lib/use-tables";

export default function HomePage() {
  const { tables, isLoading } = useTables();
  if (isLoading) return <TableList.Skeleton />;
  if (tables.length === 0) {
    return <EmptyState title="No tables booked yet" />;
  }
  return (
    <main>
      <h1>Today&apos;s tables</h1>
      <TableList tables={tables} />
    </main>
  );
}
