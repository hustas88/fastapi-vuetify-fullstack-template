<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

import PrivateLayout from "@/layouts/PrivateLayout.vue";
import PublicLayout from "@/layouts/PublicLayout.vue";

// Routes opt into a layout with `meta.layout`; anything unmarked is private,
// so forgetting the meta on a new page cannot leak it to signed-out visitors.
const route = useRoute();
const layout = computed(() => (route.meta.layout === "public" ? PublicLayout : PrivateLayout));
</script>

<template>
  <v-app>
    <component :is="layout">
      <router-view />
    </component>
  </v-app>
</template>
