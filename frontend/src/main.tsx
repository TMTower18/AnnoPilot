import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./style.css";
import "./appearance.css";
import {
  AppearanceProvider,
  initializeAppearance,
} from "./appearance/AppearanceProvider";
initializeAppearance();
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppearanceProvider>
      <App />
    </AppearanceProvider>
  </React.StrictMode>,
);
