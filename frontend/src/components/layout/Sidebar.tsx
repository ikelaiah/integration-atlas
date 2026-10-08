import { NavLink, useLocation } from "react-router-dom";
import {
  Activity,
  Boxes,
  ChevronLeft,
  Compass,
  Database,
  LayoutDashboard,
  ScanSearch,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Waypoints,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { SimpleTooltip } from "@/components/ui/tooltip";

export interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  workspaceName: string;
  isDemo: boolean;
}

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/atlas", label: "Atlas", icon: Waypoints },
  { to: "/systems", label: "Systems", icon: Boxes },
  { to: "/integrations", label: "Integrations", icon: Activity },
  { to: "/data", label: "Data", icon: Database },
  { to: "/risks", label: "Risks", icon: ShieldAlert },
  { to: "/scans", label: "Scans", icon: ScanSearch },
  { to: "/review", label: "Review", icon: ShieldCheck },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar({ collapsed, onToggle, workspaceName, isDemo }: SidebarProps) {
  const location = useLocation();

  return (
    <nav
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-line bg-surface transition-[width] duration-200 ease-out",
        collapsed ? "w-[52px]" : "w-[204px]",
      )}
      aria-label="Primary"
    >
      {/* brand */}
      <div
        className={cn(
          "flex h-[52px] items-center gap-2 border-b border-line px-3",
          collapsed && "justify-center px-0",
        )}
      >
        <div className="relative flex h-[22px] w-[22px] shrink-0 items-center justify-center">
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden>
            {/* restrained atlas/network motif: nodes + connecting arcs */}
            <circle cx="6" cy="6.5" r="2.6" fill="#4c8dff" />
            <circle cx="16" cy="5.5" r="2" fill="#2dd4bf" />
            <circle cx="15.5" cy="16" r="2.4" fill="#a78bfa" />
            <circle cx="6.5" cy="15.5" r="1.8" fill="#fbbf24" />
            <path
              d="M8.4 7.4 L13.8 6.2 M14.9 7.5 L15.2 13.2 M13.6 15.6 L8.3 15.2 M6.2 12.9 L6.4 9.2"
              stroke="#3a4756"
              strokeWidth="1.1"
              strokeLinecap="round"
            />
            <path
              d="M7.6 8.6 C10 10, 12 10.4, 14.2 8.2"
              stroke="#4c8dff"
              strokeOpacity="0.55"
              strokeWidth="1.1"
              strokeLinecap="round"
            />
          </svg>
        </div>
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <div className="truncate text-[12.5px] font-semibold leading-tight tracking-tight text-ink">
              Integration Atlas
            </div>
            <div className="truncate text-[9.5px] leading-tight text-subtle">
              {isDemo ? "Demo workspace" : "Local workspace"}
            </div>
          </div>
        )}
      </div>

      {/* nav */}
      <div className="flex-1 overflow-y-auto px-2 py-2.5">
        <div className="space-y-0.5">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active =
              item.end === true
                ? location.pathname === item.to
                : location.pathname.startsWith(item.to) && item.to !== "/";

            const link = (
              <NavLink
                key={item.to}
                to={item.to}
                className={cn(
                  "group flex items-center gap-2.5 rounded-[6px] px-2 py-[7px] text-[12px] transition-colors",
                  collapsed && "justify-center px-0",
                  active
                    ? "bg-surface-3 text-ink shadow-[0_1px_2px_rgba(0,0,0,0.22)]"
                    : "text-ink-muted hover:bg-surface-2 hover:text-ink",
                )}
              >
                <Icon
                  className={cn(
                    "h-[15px] w-[15px] shrink-0 transition-colors",
                    active ? "text-accent-strong" : "text-subtle group-hover:text-ink-muted",
                  )}
                  strokeWidth={active ? 2.1 : 1.8}
                />
                {!collapsed && <span className="truncate">{item.label}</span>}
                {!collapsed && active && (
                  <span className="ml-auto h-[5px] w-[5px] rounded-full bg-accent" />
                )}
              </NavLink>
            );

            return collapsed ? (
              <SimpleTooltip key={item.to} content={item.label} side="right">
                {link}
              </SimpleTooltip>
            ) : (
              link
            );
          })}
        </div>
      </div>

      {/* workspace footer */}
      {!collapsed && (
        <div className="border-t border-line px-3 py-2.5">
          <div className="text-[9.5px] uppercase tracking-[0.08em] text-subtle">Workspace</div>
          <div className="mt-0.5 truncate text-[11.5px] text-ink">{workspaceName}</div>
        </div>
      )}

      <button
        type="button"
        onClick={onToggle}
        className={cn(
          "flex h-[30px] items-center gap-1.5 border-t border-line px-3 text-[10.5px] text-subtle transition-colors hover:bg-surface-2 hover:text-ink",
          collapsed && "justify-center px-0",
        )}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        <ChevronLeft
          className={cn("h-3 w-3 transition-transform duration-200", collapsed && "rotate-180")}
        />
        {!collapsed && <span>Collapse</span>}
        {!collapsed && <span className="ml-auto mono text-[9px] text-subtle">⌘B</span>}
      </button>
    </nav>
  );
}

/** Compact icon rail used in the top bar for the current section. */
export function SectionIcon({ className }: { className?: string }) {
  return <Compass className={cn("h-4 w-4 text-subtle", className)} />;
}
