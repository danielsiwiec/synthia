import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";

function injectPwaTags() {
  const tags: Array<[string, Record<string, string>]> = [
    ["link", { rel: "manifest", href: "/static/manifest.json" }],
    ["link", { rel: "icon", type: "image/x-icon", href: "/static/favicon.ico" }],
    ["link", { rel: "apple-touch-icon", href: "/static/apple-touch-icon.png" }],
  ];
  for (const [tag, attrs] of tags) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    document.head.appendChild(el);
  }
}

injectPwaTags();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
