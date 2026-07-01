import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import StellarIntro from "./StellarIntro.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
    <StellarIntro />
  </React.StrictMode>
);
