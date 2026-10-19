// expect: none
export function Form({ go }: { go: () => void }) {
  return (
    <form>
      <select name="size"><option>S</option></select>
      <input type="checkbox" name="ok" />
      <button type="button" onClick={go}>Go</button>
      <div tabIndex={0} onKeyDown={go}>Focusable</div>
    </form>
  );
}
