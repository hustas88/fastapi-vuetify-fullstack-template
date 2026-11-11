<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAuth } from "@/composables/useAuth";

const route = useRoute();
const router = useRouter();
const { login } = useAuth();

const email = ref("");
const password = ref("");
const loading = ref(false);
const error = ref<string | null>(null);

async function submit(): Promise<void> {
  error.value = null;
  loading.value = true;
  try {
    await login(email.value, password.value);
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/";
    await router.push(redirect);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Unexpected error";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <v-card title="Sign in" subtitle="Use the credentials from your .env file">
    <v-card-text>
      <v-alert v-if="error" type="error" variant="tonal" class="mb-4" :text="error" />

      <v-form @submit.prevent="submit">
        <v-text-field
          v-model="email"
          type="email"
          label="Email"
          variant="outlined"
          autocomplete="username"
          class="mb-3"
          required
        />
        <v-text-field
          v-model="password"
          type="password"
          label="Password"
          variant="outlined"
          autocomplete="current-password"
          class="mb-4"
          required
        />
        <v-btn
          type="submit"
          color="primary"
          block
          size="large"
          :loading="loading"
          :disabled="!email || !password"
        >
          Sign in
        </v-btn>
      </v-form>
    </v-card-text>
    <v-card-actions class="px-4 pb-4">
      <span class="text-caption text-medium-emphasis">
        The first superuser is seeded from FIRST_SUPERUSER* on startup.
      </span>
    </v-card-actions>
  </v-card>
</template>
