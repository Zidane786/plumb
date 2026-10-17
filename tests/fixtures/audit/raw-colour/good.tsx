// expect: none
// The brand colour was #14857f before the tokens (a comment, not code). Fixes #123.
export function Faq() {
  const el = document.querySelector("#add");
  return (
    <a href="#faq" className="w-[320px] h-[48px] top-[4px] grid-cols-[1fr_2fr] bg-primary text-on-primary">
      <svg><use href="#icon-add" /><rect fill="url(#bad)" /></svg>
      Read the FAQ {el ? "" : "&#123;"}
    </a>
  );
}
