import { Alert, Button, Layout, Spin, Tag } from "@arco-design/web-react";
import { IconRefresh } from "@arco-design/web-react/icon";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { WORKBENCH_ROUTES } from "../../app/routes";

const Header = Layout.Header;
const Sider = Layout.Sider;
const Content = Layout.Content;

export function WorkbenchShell({
  children,
  status,
  apiVersion,
  loading,
  error,
  onRefresh
}: {
  children: ReactNode;
  status: string;
  apiVersion: string;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  const location = useLocation();
  const activeRoute =
    WORKBENCH_ROUTES.find((route) =>
      route.key === "home" ? location.pathname === "/" : location.pathname.startsWith(route.path.split("/")[1] ? `/${route.path.split("/")[1]}` : route.path)
    ) ?? WORKBENCH_ROUTES[0];

  return (
    <Layout className="workbench-shell">
      <Sider className="workbench-sidebar" width={204}>
        <div className="brand-block">
          <div className="brand-mark">KG</div>
          <div>
            <strong>KGTraceVis</strong>
            <span>Root-cause evidence workbench</span>
          </div>
        </div>
        <nav className="side-nav" aria-label="Main modules">
          {WORKBENCH_ROUTES.map((route) => (
            <Link
              key={route.key}
              to={route.path}
              className={`side-nav-item ${activeRoute.key === route.key ? "active" : ""}`}
            >
              <span className="side-nav-icon">{route.icon}</span>
              <span className="side-nav-label" title={route.description}>
                <strong>{route.label}</strong>
              </span>
            </Link>
          ))}
        </nav>
      </Sider>
      <Layout>
        <Header className="workbench-header">
          <div>
            <span className="eyebrow">Current Module</span>
            <h1>{activeRoute.label}</h1>
          </div>
          <div className="header-actions">
            <Tag color={status === "ok" ? "green" : "orangered"}>{status}</Tag>
            <Tag color="arcoblue">{apiVersion}</Tag>
            <Button icon={<IconRefresh />} onClick={onRefresh}>
              Refresh
            </Button>
          </div>
        </Header>
        <Content className="workbench-content">
          {error && <Alert className="shell-alert" type="error" title={error} />}
          <Spin loading={loading} className="shell-spin">
            {children}
          </Spin>
        </Content>
      </Layout>
    </Layout>
  );
}
