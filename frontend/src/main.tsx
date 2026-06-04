import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

// Self-hosted variable fonts (Geist + Geist Mono) — the documented
// open-source substitutes for the brand's proprietary Universal Sans.
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";

import "./styles/tokens.css";
import "./styles/global.css";
import "./styles/app.css";
import "./components/components.css";

import { App } from "./App";
import { queryClient } from "./lib/queryClient";

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("Root element #root not found");

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
