// expect: none
const theme = { dark: true, light:false };
export function Panel() {
  const mode = theme.dark ? "dark" : "light";
  return <div className="bg-background" data-mode={mode}>Panel</div>;
}
