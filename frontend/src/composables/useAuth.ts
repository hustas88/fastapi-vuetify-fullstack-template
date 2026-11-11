import { computed, ref } from "vue";

import { ApiError, api, clearTokens, getToken, type UserPublic } from "@/api/client";

// Module-level state: shared by every component that calls useAuth().
const user = ref<UserPublic | null>(null);
const token = ref<string | null>(getToken());
const isAuthenticated = computed(() => Boolean(token.value));

export function useAuth() {
  async function login(email: string, password: string): Promise<void> {
    await api.login(email, password);
    token.value = getToken();
    user.value = await api.get<UserPublic>("/users/me");
  }

  async function logout(): Promise<void> {
    // Revoke the refresh-token chain server-side, then drop local state.
    await api.logout();
    token.value = null;
    user.value = null;
  }

  async function refreshUser(): Promise<void> {
    if (!getToken()) {
      token.value = null;
      user.value = null;
      return;
    }
    token.value = getToken();
    try {
      user.value = await api.get<UserPublic>("/users/me");
    } catch (error) {
      // Only an authentication failure ends the session. A 500 or a transient
      // network error must not silently drop a valid token.
      if (error instanceof ApiError && error.status === 401) {
        clearTokens();
        token.value = null;
        user.value = null;
      }
    }
  }

  return { user, token, isAuthenticated, login, logout, refreshUser };
}
