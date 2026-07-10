import { Bell, Play, Loader2, User } from "lucide-react";
import { Button } from "../components/ui";

type Loading =
  | "dashboards"
  | "databases"
  | "migration"
  | null;

interface Props {
  loading: Loading;
  canMigrate: boolean;
  onStartMigration: () => void;
}

export default function Topbar({
  loading,
  canMigrate,
  onStartMigration,
}: Props) {
  return (
    <header className="topbar">

      <div className="topbar-left">

        <span className="eyebrow">
          AI Powered Dashboard Migration
        </span>

        <h1>MigrAI</h1>

      </div>

      <div className="topbar-right">

        <button className="icon-button">
          <Bell size={18}/>
        </button>

        <button className="icon-button">
          <User size={18}/>
        </button>

        <Button
          variant="primary"
          disabled={!canMigrate}
          onClick={onStartMigration}
        >
          {loading==="migration"
            ? <Loader2 className="spin" size={18}/>
            : <Play size={18}/>
          }

          Start Migration
        </Button>

      </div>

    </header>
  );
}