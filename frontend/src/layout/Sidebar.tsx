import {
  LayoutDashboard,
  RefreshCw,
  Activity,
  Settings,
  Gauge,
} from "lucide-react";

import { Button } from "../components/ui";

type View =
  | "dashboard"
  | "migration"
  | "history"
  | "settings";

interface SidebarProps {
  activeView: View;
  setActiveView: (view: View) => void;
}

export default function Sidebar({
  activeView,
  setActiveView,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-top">

        <div className="brand-card">

          <div className="brand-icon">
            <Gauge size={34} />
          </div>

          <div>
            <h2>MigrAI</h2>
            <p>Dashboard Migration</p>
          </div>

        </div>

        <nav className="sidebar-nav">

          <Button
            variant="ghost"
            nav
            active={activeView === "dashboard"}
            onClick={() => setActiveView("dashboard")}
          >
            <LayoutDashboard size={20} />
            Dashboard
          </Button>

          <Button
            variant="ghost"
            nav
            active={activeView === "migration"}
            onClick={() => setActiveView("migration")}
          >
            <RefreshCw size={20} />
            Migration
          </Button>

          <Button
            variant="ghost"
            nav
            active={activeView === "history"}
            onClick={() => setActiveView("history")}
          >
            <Activity size={20} />
            History
          </Button>

          <Button
            variant="ghost"
            nav
            active={activeView === "settings"}
            onClick={() => setActiveView("settings")}
          >
            <Settings size={20} />
            Settings
          </Button>

        </nav>

      </div>

      <div className="sidebar-footer">

        <div className="status-card">

          <div className="status-dot" />

          <div>

            <strong>System Ready</strong>

            <span>Metabase → Superset</span>

          </div>

        </div>

      </div>

    </aside>
  );
}