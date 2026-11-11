import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { Layout, NAV } from "./components/Layout";
import { AnalystPage } from "./features/analyst/AnalystPage";
import { OverviewPage } from "./features/overview/OverviewPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { SettingsPage } from "./pages/SettingsPage";
import "./index.css";

const DESCRIPTIONS: Record<string, string> = {
  "/production": "Production volume, attainment and defect rates by line and day.",
  "/downtime": "Downtime events, reasons and the equipment involved.",
  "/quality": "Quality incidents by category, severity and status.",
  "/knowledge": "Search maintenance and troubleshooting documentation with cited passages.",
  "/activity": "A timeline of agent requests, tool calls, durations and outcomes.",
  "/evaluations": "Results of the versioned evaluation dataset: tool selection, numeric accuracy, groundedness and prompt-injection resistance.",
};

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <OverviewPage /> },
      { path: "/analyst", element: <AnalystPage /> },
      { path: "/settings", element: <SettingsPage /> },
      ...NAV.filter((n) => n.availableIn).map((n) => ({
        path: n.path,
        element: <PlaceholderPage title={n.label} availableIn={n.availableIn!} description={DESCRIPTIONS[n.path] ?? ""} />,
      })),
      { path: "*", element: <PlaceholderPage title="Not found" availableIn="—" description="This page does not exist." /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
