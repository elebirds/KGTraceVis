import { ConfigProvider } from "@arco-design/web-react";
import type { ReactNode } from "react";

export function AppProviders({ children }: { children: ReactNode }) {
  return <ConfigProvider>{children}</ConfigProvider>;
}
