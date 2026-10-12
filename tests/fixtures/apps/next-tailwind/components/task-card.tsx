export function TaskCard({ title }: { title: string }) {
  return (
    <div className="bg-[#1f7a8c] p-4 rounded-[6px]">
      <h2 className="text-[15px]">{title}</h2>
      <button type="button" className="bg-blue-500">Done</button>
    </div>
  );
}
