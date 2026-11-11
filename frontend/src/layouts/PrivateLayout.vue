<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { useAuth } from "@/composables/useAuth";

const drawer = ref(true);
const router = useRouter();
const { user, logout, refreshUser } = useAuth();

// Dev-only shortcuts; folded to `null` in production builds.
const DevToolsLinks = import.meta.env.DEV
  ? defineAsyncComponent(() => import("@/components/DevToolsLinks.vue"))
  : null;

const navItems = [{ title: "Dashboard", icon: "mdi-view-dashboard-outline", to: "/" }];

onMounted(() => {
  void refreshUser();
});

function signOut(): void {
  void logout().finally(() => {
    void router.push({ name: "login" });
  });
}
</script>

<template>
  <v-app-bar flat border>
    <v-app-bar-nav-icon aria-label="Toggle navigation" @click="drawer = !drawer" />
    <v-app-bar-title class="font-weight-bold">FastAPI + Vuetify</v-app-bar-title>
    <v-spacer />

    <span class="text-body-2 text-medium-emphasis mr-3 d-none d-sm-inline">
      {{ user?.email }}
    </span>
    <v-btn variant="text" prepend-icon="mdi-logout" @click="signOut">Sign out</v-btn>
  </v-app-bar>

  <v-navigation-drawer v-model="drawer" border>
    <v-list nav density="comfortable">
      <v-list-item
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        :prepend-icon="item.icon"
        :title="item.title"
      />
    </v-list>

    <template v-if="DevToolsLinks" #append>
      <component :is="DevToolsLinks" />
    </template>
  </v-navigation-drawer>

  <v-main>
    <slot />
  </v-main>
</template>
