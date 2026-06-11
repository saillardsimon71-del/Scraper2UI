import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Fire } from "@phosphor-icons/react";
import api, { NIVEAU_STYLES, PROFIL_LABELS, STATUT_LABELS } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import ProspectSheet from "@/components/ProspectSheet";

const COLUMNS = [
  { key: "a_contacter", color: "border-t-[#002FA7]" },
  { key: "repondu", color: "border-t-emerald-500" },
  { key: "rdv", color: "border-t-violet-500" },
  { key: "gagne", color: "border-t-emerald-600" },
  { key: "perdu", color: "border-t-slate-400" },
  { key: "epuise", color: "border-t-amber-400" },
];

export default function Pipeline() {
  const [prospects, setProspects] = useState([]);
  const [stats, setStats] = useState([]);
  const [openId, setOpenId] = useState(null);
  const [dragOver, setDragOver] = useState(null);

  const load = useCallback(async () => {
    const [p, s] = await Promise.all([
      api.get("/prospects", { params: { limit: 500 } }),
      api.get("/dashboard/scenario-stats"),
    ]);
    setProspects(p.data.items);
    setStats(s.data.stats);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onDrop = async (e, statut) => {
    e.preventDefault();
    setDragOver(null);
    const id = e.dataTransfer.getData("text/plain");
    if (!id) return;
    await api.patch(`/prospects/${id}`, { statut });
    toast.success(`Déplacé vers « ${STATUT_LABELS[statut]} »`);
    load();
  };

  const grouped = COLUMNS.map((c) => ({
    ...c,
    items: prospects.filter((p) => p.statut === c.key),
  }));

  return (
    <div className="p-8 fade-up">
      <h1 className="text-4xl tracking-tighter font-bold text-[#111111]">Pipeline</h1>
      <p className="text-sm text-slate-500 mt-1 mb-6">
        Glissez-déposez les prospects entre colonnes. Stats de réponse par scénario ci-dessous.
      </p>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {stats.map((s) => (
          <div key={s.profil} data-testid={`scenario-stat-${s.profil}`} className="bg-white border border-slate-200 p-4 rounded-sm">
            <div className="text-xs uppercase tracking-[0.15em] font-semibold text-slate-500">{s.label}</div>
            <div className="flex items-baseline gap-2 mt-2">
              <span className="font-heading text-3xl font-bold tabular-nums text-[#111111]">{s.taux_reponse}%</span>
              <span className="text-[11px] text-slate-400">de réponse</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1 font-mono tabular-nums">
              {s.total} prospects · {s.contactes} contactés · {s.repondus} réponses · {s.rdv} RDV
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-6 gap-3 items-start">
        {grouped.map((col) => (
          <div
            key={col.key}
            data-testid={`kanban-col-${col.key}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(col.key);
            }}
            onDragLeave={() => setDragOver(null)}
            onDrop={(e) => onDrop(e, col.key)}
            className={`bg-white border border-slate-200 border-t-2 ${col.color} rounded-sm min-h-[300px] transition-colors ${
              dragOver === col.key ? "bg-blue-50/60" : ""
            }`}
          >
            <div className="px-3 py-2.5 border-b border-slate-100 flex items-center justify-between">
              <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-600">
                {STATUT_LABELS[col.key]}
              </span>
              <span className="font-mono text-xs tabular-nums text-slate-400">{col.items.length}</span>
            </div>
            <div className="p-2 space-y-2">
              {col.items.map((p) => (
                <div
                  key={p.id}
                  data-testid="kanban-card"
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData("text/plain", p.id)}
                  onClick={() => setOpenId(p.id)}
                  className="border border-slate-200 rounded-sm p-2.5 cursor-grab active:cursor-grabbing hover:border-[#002FA7] transition-colors bg-white"
                >
                  <div className="text-xs font-semibold text-[#111111] line-clamp-2">{p.entreprise}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">{p.ville}</div>
                  <div className="flex items-center gap-1 mt-1.5 flex-wrap">
                    <Badge variant="outline" className={`rounded-sm text-[10px] px-1 py-0 tabular-nums ${NIVEAU_STYLES[p.niveau_conversion] || ""}`}>
                      {p.niveau_conversion === "Très chaud" && <Fire size={9} weight="fill" className="mr-0.5" />}
                      {p.score_conversion}
                    </Badge>
                    <span className="text-[10px] text-slate-400">{PROFIL_LABELS[p.profil]}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <ProspectSheet prospectId={openId} onClose={() => setOpenId(null)} onChanged={load} />
    </div>
  );
}
