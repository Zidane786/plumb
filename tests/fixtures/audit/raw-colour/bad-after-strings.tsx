// expect: raw-colour@4
const open = "/* not a comment";
export const C = () => (
  <p className="bg-[#14857F]">{open}{/* a real comment */}</p>
);
