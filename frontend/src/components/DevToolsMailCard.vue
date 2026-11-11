<script setup lang="ts">
// Development-only card describing the local Mailpit inbox. Imported
// dynamically behind `import.meta.env.DEV` so it never ships to production.
</script>

<template>
  <v-card variant="tonal" height="100%">
    <v-card-item>
      <template #prepend>
        <v-icon icon="mdi-email-fast-outline" />
      </template>
      <v-card-title>Mailpit</v-card-title>
      <v-card-subtitle>Local email inbox (dev only)</v-card-subtitle>
    </v-card-item>
    <v-card-text class="text-body-2 text-medium-emphasis">
      Local development catches outgoing mail at
      <a href="http://localhost:8025" target="_blank" rel="noreferrer">localhost:8025</a>.
      The deployed stack uses a real SMTP relay instead.
    </v-card-text>
  </v-card>
</template>
