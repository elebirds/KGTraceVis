import {
  IconApps,
  IconBook,
  IconBranch,
  IconExperiment,
  IconHome
} from "@arco-design/web-react/icon";
import type { ReactNode } from "react";

export type AppRouteKey = "home" | "analysis" | "kg-studio" | "experiments";

export interface WorkbenchRoute {
  key: AppRouteKey;
  path: string;
  label: string;
  description: string;
  icon: ReactNode;
}

export const WORKBENCH_ROUTES: WorkbenchRoute[] = [
  {
    key: "home",
    path: "/",
    label: "Home",
    description: "System status and recent evidence",
    icon: <IconHome />
  },
  {
    key: "analysis",
    path: "/analysis/live",
    label: "Analysis",
    description: "Run records, inspect cases, review paths",
    icon: <IconApps />
  },
  {
    key: "kg-studio",
    path: "/kg-studio/overview",
    label: "KG Studio",
    description: "Source-grounded KG review workspace",
    icon: <IconBranch />
  },
  {
    key: "experiments",
    path: "/experiments",
    label: "Experiments",
    description: "Paper cases and artifact readiness",
    icon: <IconExperiment />
  }
];

export const ANALYSIS_TABS = [
  { key: "live", path: "/analysis/live", label: "Live Run", icon: <IconBook /> },
  { key: "history", path: "/analysis/history", label: "History", icon: <IconApps /> }
];

export const KG_STUDIO_TABS = [
  { key: "overview", path: "/kg-studio/overview", label: "Overview" },
  { key: "sources", path: "/kg-studio/sources", label: "Sources" },
  { key: "build", path: "/kg-studio/build", label: "Build" },
  { key: "graph", path: "/kg-studio/graph", label: "Graph" },
  { key: "review", path: "/kg-studio/review", label: "Review" },
  { key: "drafts", path: "/kg-studio/drafts", label: "Draft Lab" }
];
