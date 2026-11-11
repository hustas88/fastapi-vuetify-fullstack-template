<script setup lang="ts">
// Development-only shortcuts. This module is imported dynamically behind
// `import.meta.env.DEV`, so it (and any local tooling references) is removed
// from production builds.
const links = [
  { title: "API docs", icon: "mdi-api", href: "http://localhost:8000/docs" },
  { title: "Mailpit (dev)", icon: "mdi-email-outline", href: "http://localhost:8025" },
];
</script>

<template>
  <v-list nav density="compact">
    <v-list-item
      v-for="link in links"
      :key="link.href"
      :href="link.href"
      target="_blank"
      rel="noreferrer"
      :prepend-icon="link.icon"
      :title="link.title"
    />
  </v-list>
</template>
