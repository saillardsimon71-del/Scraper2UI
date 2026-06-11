import { NavLink, Outlet } from "react-router-dom";
import {
  SunHorizon,
  UsersThree,
  Kanban,
  MagnifyingGlass,
  UploadSimple,
  ChatsCircle,
  GearSix,
  Crosshair,
  EnvelopeOpen,
} from "@phosphor-icons/react";

const NAV = [
  { to: "/", label: "File du jour", icon: SunHorizon, testid: "nav-file-du-jour" },
  { to: "/prospects", label: "Prospects", icon: UsersThree, testid: "nav-prospects" },
  { to: "/pipeline", label: "Pipeline", icon: Kanban, testid: "nav-pipeline" },
  { to: "/reponses", label: "Réponses", icon: EnvelopeOpen, testid: "nav-reponses" },
  { to: "/scraper", label: "Scraper", icon: MagnifyingGlass, testid: "nav-scraper" },
  { to: "/import", label: "Import", icon: UploadSimple, testid: "nav-import" },
  { to: "/scenarios", label: "Séquences", icon: ChatsCircle, testid: "nav-scenarios" },
  { to: "/parametres", label: "Paramètres", icon: GearSix, testid: "nav-parametres" },
];

export default function Layout() {
  return (
    <div className="flex min-h-screen">
      <aside className="w-60 shrink-0 bg-[#111111] text-white flex flex-col fixed inset-y-0 left-0 z-30">
        <div className="px-6 py-7 flex items-center gap-3 border-b border-white/10">
          <Crosshair size={26} weight="bold" className="text-[#25D366]" />
          <div>
            <div className="font-heading font-bold text-lg leading-none tracking-tight">COCKPIT</div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-white/50 mt-1">Prospection</div>
          </div>
        </div>
        <nav className="flex-1 py-6 px-3 space-y-1">
          {NAV.map(({ to, label, icon: Icon, testid }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              data-testid={testid}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 text-sm rounded-sm transition-colors duration-150 ${
                  isActive
                    ? "bg-white text-[#111111] font-semibold"
                    : "text-white/60 hover:text-white hover:bg-white/5"
                }`
              }
            >
              <Icon size={18} weight="bold" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-6 py-5 border-t border-white/10 text-[11px] text-white/40">
          LinkedIn & WhatsApp semi-auto
          <br />
          Artisans · France
        </div>
      </aside>
      <main className="flex-1 ml-60 min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
