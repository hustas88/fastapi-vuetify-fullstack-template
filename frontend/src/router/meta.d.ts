import "vue-router";

// Typed route meta, so layouts and guards read the same contract.
declare module "vue-router" {
  interface RouteMeta {
    /** Document title, also used for `document.title`. */
    title?: string;
    /** Which shell wraps the view. Defaults to `private`. */
    layout?: "public" | "private";
    /** Redirects to the login page when there is no token. */
    requiresAuth?: boolean;
    /** Redirects away (to the dashboard) when there *is* a token. */
    guestOnly?: boolean;
  }
}
