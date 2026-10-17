const dishes: { name: string }[] = [{ name: "Soupe à l’oignon" }];

export default function MenuPage() {
  if (dishes.length === 0) return <p>Pas de plats aujourd’hui</p>;
  return (
    <main>
      <h1>Menü du jour</h1>
      <ul>
        {dishes.map((d) => (
          <li key={d.name}>{d.name}</li>
        ))}
      </ul>
    </main>
  );
}
