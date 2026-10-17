<!-- expect: none -->
<script>
  export let active = false;
</script>
<a href="#top" class="bg-primary p-2" class:rounded-md={active}>Top</a>
<style>
  a { color: var(--color-on-surface); border-radius: var(--radius-md); }
</style>
