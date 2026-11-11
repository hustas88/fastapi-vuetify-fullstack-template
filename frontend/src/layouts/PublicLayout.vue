<script setup lang="ts">
import { defineAsyncComponent } from "vue";

// Dev-only shortcuts; folded to `null` in production builds.
const DevToolsLinks = import.meta.env.DEV
  ? defineAsyncComponent(() => import("@/components/DevToolsLinks.vue"))
  : null;
</script>

<template>
  <v-main>
    <div class="public-shell">
      <header class="text-center mb-6">
        <v-icon icon="mdi-shield-account" size="44" color="primary" />
        <h1 class="text-h6 font-weight-bold mt-2">FastAPI + Vuetify</h1>
      </header>

      <div class="w-100">
        <slot />
      </div>

      <component :is="DevToolsLinks" v-if="DevToolsLinks" class="mt-8 w-100" />
    </div>
  </v-main>
</template>

<style scoped>
.public-shell {
  min-height: 100dvh;
  width: 100%;
  max-width: 460px;
  margin-inline: auto;
  padding: 32px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
</style>
