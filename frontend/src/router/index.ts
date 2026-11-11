import { createRouter, createWebHistory } from "vue-router";

import { getToken } from "@/api/client";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "dashboard",
      component: () => import("@/views/DashboardView.vue"),
      meta: { title: "Dashboard", requiresAuth: true },
    },
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { title: "Sign in", layout: "public", guestOnly: true },
    },
    // Public, unauthenticated flows that reuse PublicLayout:
    //   /forgot-password      request a reset link
    //   /reset-password       set a new password (token from the email)
    //   /accept-invitation    onboarding: confirm the invited password
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach((to) => {
  const authenticated = Boolean(getToken());

  if (to.meta.requiresAuth && !authenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.meta.guestOnly && authenticated) {
    return { name: "dashboard" };
  }
  return true;
});

router.afterEach((to) => {
  const title = to.meta.title ?? "Dashboard";
  document.title = `${title} · FastAPI + Vuetify`;
});

export default router;
