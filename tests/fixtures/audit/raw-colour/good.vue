<!-- expect: none -->
<template>
  <a href="#top" class="bg-primary text-on-primary p-4 rounded-md">Back to top</a>
</template>
<script setup lang="ts">
const id = "main";
</script>
<style scoped>
a { color: var(--color-primary); transition: color 150ms var(--ease-out); }
</style>
