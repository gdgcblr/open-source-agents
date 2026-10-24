import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "survey-core/survey-core.min.css";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
