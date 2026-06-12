import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  TrendUp,
  CurrencyEur,
  Trophy,
  ChartBar,
  ArrowRight,
  Users,
} from "@phosphor-icons/react";
import api from "@/lib/api";

function KpiCard({ label, value, sub, accent, icon: Icon }) {
  return (
    <div className="bg-white border border-slate-200 p-5 rounded-sm">
      <div className="flex items-start justify-between">
        <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500">{label}</div>
        {Icon && <Icon size={18} className="text-slate-300" />}
      </div>
      <div className={`font-heading text-4xl font-bold mt-2 tabular-nums ${accent || "text-[#111111]"}`}>
        {value}
      </div>
      {sub && <div className="text-xs text-slate-400 mt-1">{sub}</div>}
    </div>
  );
}

function FunnelBar({ label, value, max, color }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <div className="w-28 text-xs text-slate-600 text-right shrink-0">{label}</div>
      <div className="flex-1 bg-slate-100 h-7 rounded-sm overflow-hidden">
        <div
          className={`h-7 rounded-sm flex items-center px-3 text-xs font-semibold text-white transition-all duration-500 ${color}`}
          style={{ width: `${Math.max(pct, 4)}%` }}
        >
          {value}
        </div>
      </div>
      <div className="w-10 text-xs text-slate-400 tabular-nums text-right">{pct}%</div>
    </div>
  );
}

const PROFIL_LABELS = {
  pas_de_site: "Pas de site",
  site_ancien: "Site ancien",
  signal_chaud: "Signal chaud",
  site_moyen: "Site moyen",
};

export default function Business() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await api.get("/dashboard/business");
      setData(res.data);
    } catch {
      toast.error("Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="p-8 text-sm text-slate-400">Chargement…</div>;
  if (!data) return null;

  const { entonnoir, ca, raisons_refus, par_profil, derniers_gagnes,
    taux_reponse, taux_rdv, taux_signature } = data;

  return (
    <div className="p-8 fade-up">
      <div className="mb-8">
        <h1 className="text-4xl tracking-tighter font-bold text-[#111111]">Business</h1>
        <p className="text-sm text-slate-500 mt-1">Entonnoir de conversion, chiffre d'affaires et analyse des refus.</p>
      </div>

      {/* KPIs CA */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KpiCard
          label="CA total signé"
          value={ca.total > 0 ? `${ca.total.toLocaleString("fr-FR")} €` : "—"}
          sub={ca.count > 0 ? `${ca.count} contrat(s)` : "Aucun client signé"}
          accent="text-emerald-600"
          icon={CurrencyEur}
        />
        <KpiCard
          label="Panier moyen"
          value={ca.moyen > 0 ? `${ca.moyen.toLocaleString("fr-FR")} €` : "—"}
          sub="par contrat signé"
          icon={TrendUp}
        />
        <KpiCard
          label="Taux de réponse"
          value={entonnoir.contactes > 0 ? `${taux_reponse}%` : "—"}
          sub={`${entonnoir.repondus} / ${entonnoir.contactes} contactés`}
          icon={Users}
        />
        <KpiCard
          label="Taux de signature"
          value={entonnoir.rdv > 0 ? `${taux_signature}%` : "—"}
          sub={entonnoir.rdv > 0 ? `sur ${entonnoir.rdv} RDV` : "Aucun RDV encore"}
          icon={Trophy}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Entonnoir de conversion */}
        <div className="bg-white border border-slate-200 rounded-sm p-6">
          <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-5 flex items-center gap-2">
            <ChartBar size={14} /> Entonnoir de conversion
          </div>
          <div className="space-y-3">
            {[
              { label: "Prospects total", value: entonnoir.total, color: "bg-slate-400" },
              { label: "Contactés", value: entonnoir.contactes, color: "bg-blue-400" },
              { label: "Ont répondu", value: entonnoir.repondus, color: "bg-indigo-500" },
              { label: "RDV pris", value: entonnoir.rdv, color: "bg-violet-500" },
              { label: "Clients signés", value: entonnoir.gagnes, color: "bg-emerald-500" },
            ].map(({ label, value, color }) => (
              <FunnelBar key={label} label={label} value={value} max={entonnoir.total} color={color} />
            ))}
          </div>
          <div className="mt-5 pt-4 border-t border-slate-100 flex items-center gap-4 text-xs text-slate-500">
            <span>Réponse → RDV : <strong className="text-slate-700">{taux_rdv}%</strong></span>
            <ArrowRight size={12} className="text-slate-300" />
            <span>RDV → Signé : <strong className="text-slate-700">{taux_signature}%</strong></span>
          </div>
        </div>

        {/* Raisons de refus */}
        <div className="bg-white border border-slate-200 rounded-sm p-6">
          <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-5">
            Raisons de refus
          </div>
          {raisons_refus.length === 0 ? (
            <div className="text-sm text-slate-400 italic">
              Aucun refus enregistré — utilisez le bouton "Perdu / Refus" dans la file du jour pour collecter ces données.
            </div>
          ) : (
            <div className="space-y-3">
              {raisons_refus.map(({ raison, n }, i) => {
                const max = raisons_refus[0].n;
                const pct = Math.round((n / max) * 100);
                return (
                  <div key={i} className="flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-slate-700 truncate">{raison}</span>
                        <span className="text-xs font-mono font-semibold text-slate-500 ml-2 shrink-0">{n}</span>
                      </div>
                      <div className="h-1.5 bg-slate-100 rounded-full">
                        <div className="h-1.5 bg-red-300 rounded-full transition-all duration-500"
                          style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Conversion par profil */}
        <div className="bg-white border border-slate-200 rounded-sm p-6">
          <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-5">
            Taux de conversion par profil
          </div>
          {Object.keys(par_profil).length === 0 ? (
            <div className="text-sm text-slate-400 italic">Pas encore de données.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-400 text-left border-b border-slate-100">
                  <th className="pb-2 font-medium">Profil</th>
                  <th className="pb-2 font-medium text-right">Total</th>
                  <th className="pb-2 font-medium text-right">Réponse</th>
                  <th className="pb-2 font-medium text-right">Signés</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {Object.entries(par_profil).map(([profil, stats]) => (
                  <tr key={profil}>
                    <td className="py-2.5 text-slate-700">{PROFIL_LABELS[profil] || profil}</td>
                    <td className="py-2.5 text-right font-mono text-slate-500">{stats.total}</td>
                    <td className="py-2.5 text-right">
                      <span className={`font-mono font-semibold ${stats.taux_reponse >= 10 ? "text-emerald-600" : "text-slate-500"}`}>
                        {stats.taux_reponse}%
                      </span>
                    </td>
                    <td className="py-2.5 text-right">
                      <span className={`font-mono font-semibold ${stats.taux_conversion >= 5 ? "text-emerald-600" : "text-slate-400"}`}>
                        {stats.taux_conversion}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Derniers clients gagnés */}
        <div className="bg-white border border-slate-200 rounded-sm p-6">
          <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-5 flex items-center gap-2">
            <Trophy size={14} weight="fill" className="text-emerald-500" /> Derniers clients gagnés
          </div>
          {derniers_gagnes.length === 0 ? (
            <div className="text-sm text-slate-400 italic">
              Aucun client signé pour le moment. Marquez un prospect "Gagné" avec le montant du contrat pour voir apparaître vos résultats ici.
            </div>
          ) : (
            <div className="space-y-3">
              {derniers_gagnes.map((c, i) => (
                <div key={i} className="flex items-center justify-between border-b border-slate-50 pb-3 last:border-0 last:pb-0">
                  <div>
                    <div className="text-sm font-semibold text-[#111111]">{c.entreprise}</div>
                    <div className="text-xs text-slate-400">{c.metier} · {c.ville}</div>
                  </div>
                  <div className="text-right">
                    {c.ca_contrat > 0 ? (
                      <div className="text-sm font-bold text-emerald-600">{c.ca_contrat.toLocaleString("fr-FR")} €</div>
                    ) : (
                      <div className="text-xs text-slate-400">montant n/a</div>
                    )}
                    <div className="text-[10px] text-slate-400">
                      {new Date(c.created_at).toLocaleDateString("fr-FR")}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
