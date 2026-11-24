import React, { useEffect } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import TopBar from "./TopBar.jsx";
import { useLibrary } from "./bridge.js";
import "./index.css";

function TopBarSurface() {
  const { bridge } = useLibrary();
  const surface = new URLSearchParams(window.location.search).get("surface") || "all";
  useEffect(() => {
    document.documentElement.classList.add("av-topbar-document");
    return () => document.documentElement.classList.remove("av-topbar-document");
  }, []);
  return <TopBar bridge={bridge} surface={surface} />;
}

const surface = new URLSearchParams(window.location.search).get("surface");
createRoot(document.getElementById("root")).render(
  <React.StrictMode>{surface === "toolbar" || surface === "nav" ? <TopBarSurface /> : <App />}</React.StrictMode>,
);
