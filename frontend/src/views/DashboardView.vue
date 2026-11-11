<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref } from "vue";

import { API_BASE, api, type Message } from "@/api/client";

// Mailpit is a local-development tool. Folding on `import.meta.env.DEV` keeps
// the component out of production bundles entirely.
const DevToolsMailCard = import.meta.env.DEV
  ? defineAsyncComponent(() => import("@/components/DevToolsMailCard.vue"))
  : null;

const health = ref<"checking" | "ok" | "down">("checking");

const apiBase = computed(() => API_BASE);

onMounted(async () => {
  try {
    await api.get<Message>("/health/");
    health.value = "ok";
  } catch {
    health.value = "down";
  }
});
</script>

<template>
  <v-container class="py-8" max-width="1100">
    <header class="mb-6">
      <h1 class="text-h4 font-weight-bold">Dashboard</h1>
      <p class="text-body-2 text-medium-emphasis">
        Vite + Vue 3 + Vuetify talking to FastAPI through {{ apiBase }}
      </p>
    </header>

    <v-row>
      <v-col cols="12" md="4">
        <v-card variant="tonal" color="primary" height="100%">
          <v-card-item>
            <template #prepend>
              <v-icon icon="mdi-heart-pulse" />
            </template>
            <v-card-title>Backend</v-card-title>
            <v-card-subtitle>Health check</v-card-subtitle>
          </v-card-item>
          <v-card-text>
            <v-chip
              :color="health === 'ok' ? 'success' : health === 'down' ? 'error' : 'warning'"
              :prepend-icon="
                health === 'ok' ? 'mdi-check' : health === 'down' ? 'mdi-alert' : 'mdi-progress-clock'
              "
            >
              {{ health === "ok" ? "healthy" : health === "down" ? "unreachable" : "checking…" }}
            </v-chip>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="4">
        <v-card variant="tonal" height="100%">
          <v-card-item>
            <template #prepend>
              <v-icon icon="mdi-database" />
            </template>
            <v-card-title>PostgreSQL</v-card-title>
            <v-card-subtitle>Fresh database</v-card-subtitle>
          </v-card-item>
          <v-card-text class="text-body-2 text-medium-emphasis">
            Set <code>POSTGRES_*</code> in <code>.env</code>. Tables are created on startup while
            <code>AUTO_CREATE_SCHEMA=true</code>.
          </v-card-text>
        </v-card>
      </v-col>

      <v-col v-if="DevToolsMailCard" cols="12" md="4">
        <component :is="DevToolsMailCard" />
      </v-col>
    </v-row>
  </v-container>
</template>
