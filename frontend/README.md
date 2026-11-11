# @app/frontend

Vue 3 + Vuetify 4 + Vite + TypeScript, part of the pnpm workspace.

```bash
pnpm install                 # from the repo root
pnpm --filter @app/frontend dev        # http://localhost:5173
pnpm --filter @app/frontend build      # -> frontend/dist
pnpm --filter @app/frontend typecheck  # vue-tsc --noEmit
```

The dev server proxies `/api` to `VITE_PROXY_TARGET` (default
`http://localhost:8000`). In production, build with an absolute
`VITE_API_URL` and upload `frontend/dist` to the S3 static website.

## Layout

```
src/
  api/client.ts        # fetch wrapper, token storage, typed endpoints
  composables/         # useAuth()
  layouts/
    PublicLayout.vue   # centred card, no chrome — sign in / reset / onboarding
    PrivateLayout.vue  # app bar + navigation drawer
  plugins/vuetify.ts   # theme setup
  router/              # routes + typed meta + guards
  views/               # Dashboard, Login
  App.vue              # renders PublicLayout or PrivateLayout from meta.layout
```

## Public vs private

A route picks its shell with `meta.layout`; anything unmarked renders inside
`PrivateLayout`.

| Route | `meta` |
| ----- | ------ |
| `/` (dashboard) | `{ requiresAuth: true }` |
| `/login` | `{ layout: "public", guestOnly: true }` |

`requiresAuth` redirects signed-out visitors to `/login?redirect=…` and
`guestOnly` sends a signed-in visitor back to the dashboard. Meta is typed in
`src/router/meta.d.ts`, so a typo fails the typecheck.

Planned public flows (`/forgot-password`, `/reset-password`,
`/accept-invitation`) only need a view plus a route record with
`meta: { layout: "public" }`; the guard already covers them.
