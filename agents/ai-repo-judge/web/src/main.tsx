import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import "./index.css";
import Detail from "./pages/Detail";
import Insights from "./pages/Insights";
import Methodology from "./pages/Methodology";
import Overview from "./pages/Overview";

// HashRouter: deep links like #/pr/42 work on static hosts (GitHub Pages) with no server rewrites.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HashRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/pr/:id" element={<Detail />} />
          <Route path="/insights" element={<Insights />} />
          <Route path="/methodology" element={<Methodology />} />
          <Route path="*" element={<Overview />} />
        </Routes>
      </Layout>
    </HashRouter>
  </StrictMode>,
);
