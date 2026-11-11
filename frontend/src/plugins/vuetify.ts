import { createVuetify } from "vuetify";
import "vuetify/styles";
import "@mdi/font/css/materialdesignicons.css";

const vuetify = createVuetify({
  theme: {
    defaultTheme: "system",
  },
  defaults: {
    VBtn: { rounded: "lg" },
    VCard: { rounded: "lg" },
  },
});

export default vuetify;
