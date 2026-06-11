import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  WhatsappLogo,
  LinkedinLogo,
  Phone,
  CheckCircle,
  ArrowBendUpRight,
  Eye,
  Fire,
} from "@phosphor-icons/react";
import api, { NIVEAU_STYLES, PROFIL_LABELS } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import ProspectSheet from "@/components/ProspectSheet";

function StatCard({ label, value, accent }) {
  return (
    <div className="bg-white border border-slate-200 p-5 rounded-sm">
      <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500">{label}</div>
      <div className={`font-heading text-4xl font-bold mt-2 tabular-nums ${accent || "text-[#111111]"}`}>
        {value}
      </div>
    </div>
  );
}

export default function FileDuJour() {
  const [stats, setStats] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState(null);

  const load = useCallback(async () => {
    try {
      const [s, q] = await Promise.all([api.get("/dashboard/stats"), api.get("/queue")]);
      setStats(s.data);
      setItems(q.data.items);
    } catch {
      toast.error("Erreur de chargement de la file");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const doAction = async (id, type, label) => {
    try {
      await api.post(`/prospects/${id}/action`, { type });
      toast.success(label);
      load();
    } catch {
      toast.error("Action impossible");
    }
  };

  const openWhatsApp = (item) => {
    if (!item.wa_link) {
      toast.error("Pas de numéro de téléphone pour ce prospect");
      return;
    }
    window.open(item.wa_link, "_blank");
  };

  const openLinkedIn = async (item) => {
    try {
      await navigator.clipboard.writeText(item.message);
      toast.success("Message copié — collez-le dans LinkedIn");
    } catch {
      /* clipboard refusé */
    }
    window.open(item.linkedin_link, "_blank");
  };

  return (
    <div className="p-8 fade-up">
      <div className="flex items-end justify-between mb-8">
        <div>
          <h1 className="text-4xl tracking-tighter font-bold text-[#111111]">File du jour</h1>
          <p className="text-sm text-slate-500 mt-1">
            {new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })} —
            actions manuelles WhatsApp, LinkedIn & appels, triées par score. Les prospects avec email sont gérés par le pilote automatique.
          </p>
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatCard label="À contacter aujourd'hui" value={stats.file_du_jour} accent="text-[#002FA7]" />
          <StatCard label="Envoyés aujourd'hui" value={stats.envoyes_aujourdhui} />
          <StatCard label="Réponses" value={stats.repondus} accent="text-emerald-600" />
          <StatCard label="Taux de réponse" value={`${stats.taux_reponse}%`} />
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-sm">
        {loading ? (
          <div className="p-12 text-center text-slate-400 text-sm">Chargement…</div>
        ) : items.length === 0 ? (
          <div className="p-16 text-center">
            <CheckCircle size={40} className="mx-auto text-emerald-500 mb-3" weight="duotone" />
            <div className="font-heading text-xl font-semibold">File vide — tout est à jour 🎉</div>
            <p className="text-sm text-slate-500 mt-2">
              Lancez le scraper ou importez un fichier pour alimenter la file.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-200">
            {items.map((item, i) => {
              const p = item.prospect;
              return (
                <li
                  key={p.id}
                  data-testid="queue-row"
                  className="px-5 py-4 hover:bg-slate-50 transition-colors duration-150"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-12 text-center shrink-0">
                      <div className="font-mono font-semibold text-lg tabular-nums text-[#111111]">
                        {p.score_conversion}
                      </div>
                      <div className="text-[10px] uppercase text-slate-400">score</div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-[#111111] truncate">{p.entreprise}</span>
                        <Badge variant="outline" className={`rounded-sm text-[11px] ${NIVEAU_STYLES[p.niveau_conversion] || ""}`}>
                          {p.niveau_conversion === "Très chaud" && <Fire size={11} weight="fill" className="mr-1" />}
                          {p.niveau_conversion}
                        </Badge>
                        <Badge variant="outline" className="rounded-sm text-[11px] text-slate-600">
                          {PROFIL_LABELS[p.profil] || p.profil}
                        </Badge>
                        <span className="text-xs text-slate-400 font-mono">
                          étape {item.etape}/{item.total_etapes} · {item.canal}
                        </span>
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5 truncate">
                        {p.metier} · {p.ville} {p.telephone && `· ${p.telephone}`}
                        {p.signal_principal && ` · ⚡ ${p.signal_principal}`}
                      </div>
                      <div className="text-xs text-slate-400 mt-1 line-clamp-1 italic">“{item.message}”</div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {item.canal === "whatsapp" && (
                        <Button
                          data-testid="btn-whatsapp-send"
                          size="sm"
                          className="bg-[#25D366] hover:bg-[#1DA851] text-white rounded-sm h-8"
                          onClick={() => openWhatsApp(item)}
                          disabled={!item.wa_link}
                          title={item.wa_link ? "Ouvrir WhatsApp avec le message pré-rempli" : "Pas de téléphone"}
                        >
                          <WhatsappLogo size={16} weight="fill" />
                        </Button>
                      )}
                      {item.canal === "linkedin" && (
                        <Button
                          data-testid="btn-linkedin-open"
                          size="sm"
                          className="bg-[#0A66C2] hover:bg-[#004182] text-white rounded-sm h-8"
                          onClick={() => openLinkedIn(item)}
                          title="Copier le message + ouvrir LinkedIn"
                        >
                          <LinkedinLogo size={16} weight="fill" />
                        </Button>
                      )}
                      {item.canal === "telephone" && (
                        <Button
                          data-testid="btn-telephone-call"
                          size="sm"
                          className="bg-[#111111] hover:bg-slate-800 text-white rounded-sm h-8"
                          onClick={() => (window.location.href = `tel:${p.telephone}`)}
                          title={`Appeler ${p.telephone} — le message sert de script d'appel`}
                        >
                          <Phone size={16} weight="fill" />
                        </Button>
                      )}
                      <Button
                        data-testid="btn-mark-sent"
                        size="sm"
                        variant="outline"
                        className="rounded-sm h-8 text-emerald-700 border-emerald-300 hover:bg-emerald-50"
                        onClick={() => doAction(p.id, "envoye", "Marqué envoyé — prochaine relance planifiée")}
                        title="Marquer envoyé"
                      >
                        <CheckCircle size={16} weight="bold" />
                      </Button>
                      <Button
                        data-testid="btn-skip"
                        size="sm"
                        variant="ghost"
                        className="rounded-sm h-8 text-slate-400"
                        onClick={() => doAction(p.id, "skip", "Reporté à demain")}
                        title="Reporter à demain"
                      >
                        <ArrowBendUpRight size={16} />
                      </Button>
                      <Button
                        data-testid="btn-view-prospect"
                        size="sm"
                        variant="ghost"
                        className="rounded-sm h-8"
                        onClick={() => setOpenId(p.id)}
                        title="Détails"
                      >
                        <Eye size={16} />
                      </Button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <ProspectSheet prospectId={openId} onClose={() => setOpenId(null)} onChanged={load} />
    </div>
  );
}
