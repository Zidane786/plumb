import { TaskCard } from "../components/task-card";
import { StatusBadge } from "../components/status-badge";

const tasks = ["Order supplies", "Call the landlord"];

export default function Home() {
  return (
    <main className="p-4">
      <h1>Today&apos;s tasks</h1>
      {tasks.length === 0 ? (
        <p>No tasks yet</p>
      ) : (
        <ul>
          {tasks.map((t) => (
            <li key={t}>
              <TaskCard title={t} />
              <StatusBadge label="Open" />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
