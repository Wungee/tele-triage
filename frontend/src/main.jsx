import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import Legal from "./components/Legal.jsx";
import "./styles.css";

const route = window.location.pathname.replace(/^\/+|\/+$/g, "");

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {route === "terms" || route === "privacy" ? <Legal page={route} /> : <App />}
  </React.StrictMode>
);
