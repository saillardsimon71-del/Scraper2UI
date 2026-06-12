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
  Warning,
  Leaf,
  Bell,
  TrendingUp,
  CurrencyEur,
  X,
} from "@phosphor-icons/react";
import api, { NIVEAU_STYLES, PROFIL_LABELS } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import ProspectSheet from "@/components/ProspectSheet";

const RAISONS_REFUS_SUGGESTIONS = [
  "Trop cher",
  "Déjà quelqu'un",
  "Pas intéressé",
  "Rappeler plus tard",
  "A déjà un site récent",
  "Arrête l'activité",
  "Pas de réponse x3",
];

function StatCard({ label, value, accent, sub }) {
  return (
    <div className="bg-white border border-slate-200 p-5 rounded-sm">
      <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500">{label}</div>
      <div className={`font-heading text-4xl font-bold mt-2 tabular-nums ${accent || "text-[#111111]"}`}>
        {value}
      </div>
      {sub && <div className="text-xs text-slate-400 mt-1">{sub}</div>}
    </div>
  );
}

function RappelModal({ item, onClose, onConfirm }) {
  const [jours, setJours] = useState(7);
  const opts = [1, 3, 7, 14, 30, 60];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-sm border border-slate-200 shadow-xl p-6 w-80">
        <div className="flex items-center justify-between mb-4">
          <div className="font-semibold text-[#111111]">Rappeler dans…</div>
          <button onClick={onClose}><X size={16} className="text-slate-400" /></button>
        </div>
        <p className="text-xs text-slate-500 mb-4">{item.prospect.entreprise} · {item.prospect.ville}</p>
        <div className="flex flex-wrap gap-2 mb-5">
          {opts.map((j) => (
            <button
              key={j}
              onClick={() => setJours(j)}
              className={`px-3 py-1.5 text-sm rounded-sm border transition-colors ${jours === j ? "bg-[#002FA7] text-white border-[#002FA7]" : "border-slate-200 text-slate-700 hover:border-[#002FA7]"}`}
            >
              {j === 1 ? "Demain" : j < 7 ? `${j} jours` : j === 7 ? "1 semaine" : j === 14 ? "2 semaines" : j === 30 ? "1 mois" : "2 mois"}
            </button>
          ))}
        </div>
        <Button className="w-full bg-[#002FA7] hover:bg-[#001f7a] text-white rounded-sm" onClick={() => onConfirm(jours)}>
          <Bell size={15} className="mr-2" /> Programmer le rappel
        </Button>
      </div>
    </div>
  );
}

function PerduModal({ item, onClose, onConfirm }) {
  const [raison, setRaison] = useState("");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-sm border border-slate-200 shadow-xl p-6 w-80">
        <div className="flex items-center justify-between mb-4">
          <div className="font-semibold text-[#111111]">Raison du refus</div>
          <button onClick={onClose}><X size={16} className="text-slate-400" /></button>
        </div>
        <p className="text-xs text-slate-500 mb-3">{item.prospect.entreprise}</p>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {RAISONS_REFUS_SUGGESTIONS.map((r) => (
            <button key={r} onClick={() => setRaison(r)}
              className={`px-2.5 py-1 text-xs rounded-sm border transition-colors ${raison === r ? "bg-red-600 text-white border-red-600" : "border-slate-200 text-slate-600 hover:border-red-300"}`}>
              {r}
            </button>
          ))}
        </div>
        <input
          value={raison}
          onChange={e => setRaison(e.target.value)}
          placeholder="Autre raison…"
          className="w-full border border-slate-200 rounded-sm px-3 py-2 text-sm mb-4 outline-none focus:border-[#002FA7]"
        />
        <Button className="w-full bg-slate-800 hover:bg-slate-900 text-white rounded-sm" onClick={() => onConfirm(raison)}>
          Enregistrer
        </Button>
      </div>
    </div>
  );
}

function GagneModal({ item, onClose, onConfirm }) {
  const [montant, setMontant] = useState("");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-sm border border-slate-200 shadow-xl p-6 w-72">
        <div className="flex items-center justify-between mb-4">
          <div className="font-semibold text-emerald-700">🎉 Client gagné !</div>
          <button onClick={onClose}><X size={16} className="text-slate-400" /></button>
        </div>
        <p className="text-xs text-slate-500 mb-3">{item.prospect.entreprise} · {item.prospect.ville}</p>
        <label className="text-xs text-slate-500 block mb-1">Montant du contrat (€)</label>
        <div className="relative mb-4">
          <CurrencyEur size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="number"
            value={montant}
            onChange={e => setMontant(e.target.value)}
            placeholder="300"
            className="w-full border border-slate-200 rounded-sm pl-8 pr-3 py-2 text-sm outline-none focus:border-emerald-500"
          />
        </div>
        <Button className="w-full bg-emerald-600 hover:bg-emerald-700 text-white rounded-sm" onClick={() => onConfirm(montant ? parseFloat(montant) : null)}>
          <CheckCircle size={15} className="mr-2" /> Confirmer
        </Button>
      </div>
    </div>
  );
}

export default function FileDuJour() {
  const [stats, setStats] = useState(null);
  const [bizStats, setBizStats] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState(null);
  const [rappelItem, setRappelItem] = useState(null);
  const [perduItem, setPerduItem] = useState(null);
  const [gagneItem, setGagneItem] = useState(null);

  const load = useCallback(async () => {
    try {
      const [s, q, b] = await Promise.all([
        api.get("/dashboard/stats"),
        api.get("/queue"),
        api.get("/dashboard/business"),
      ]);
      setStats(s.data);
      setItems(q.data.items);
      setBizStats(b.data);
    } catch {
      toast.error("Erreur de chargement de la file");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const doAction = async (id, type, label, extra = {}) => {
    try {
      await api.post(`/prospects/${id}/action`, { type, ...extra });
      toast.success(label);
      load();
    } catch {
      toast.error("Action impossible");
    }
  };

  const handleRappel = async (jours) => {
    await doAction(rappelItem.prospect.id, "rappel", `Rappel programmé dans ${jours} jour(s)`, { rappel_dans_jours: jours });
    setRappelItem(null);
  };

  const handlePerdu = async (raison) => {
    await doAction(perduItem.prospect.id, "perdu", "Marqué perdu", { raison_refus: raison });
    setPerduItem(null);
  };

  const handleGagne = async (ca) => {
    await doAction(gagneItem.prospect.id, "gagne", `Client gagné 🎉${ca ? ` — ${ca} €` : ""}`, { ca_contrat: ca });
    setGagneItem(null);
  };

  const openWhatsApp = (item) => {
    if (!item.wa_link) { toast.error("Pas de numéro de téléphone pour ce prospect"); return; }
    window.open(item.wa_link, "_blank");
  };

  const openLinkedIn = async (item) => {
    try { await navigator.clipboard.writeText(item.message); toast.success("Message copié — collez-le dans LinkedIn"); } catch { /* clipboard refusé */ }
    window.open(item.linkedin_link, "_blank");
  };

  return (
    <div className="p-8 fade-up">
      {rappelItem && <RappelModal item={rappelItem} onClose={() => setRappelItem(null)} onConfirm={handleRappel} />}
      {perduItem && <PerduModal item={perduItem} onClose={() => setPerduItem(null)} onConfirm={handlePerdu} />}
      {gagneItem && <GagneModal item={gagneItem} onClose={() => setGagneItem(null)} onConfirm={handleGagne} />}

      <div className="flex items-end justify-between mb-8">
        <div>
          <h1 className="text-4xl tracking-tighter font-bold text-[#111111]">File du jour</h1>
          <p className="text-sm text-slate-500 mt-1">
            {new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })} —
            actions manuelles WhatsApp, LinkedIn & appels, triées par score.
          </p>
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <StatCard label="À contacter aujourd'hui" value={stats.file_du_jour} accent="text-[#002FA7]" />
          <StatCard label="Envoyés aujourd'hui" value={stats.envoyes_aujourdhui} />
          <StatCard label="Réponses totales" value={stats.repondus} accent="text-emerald-600" />
          <StatCard label="Taux de réponse" value={`${stats.taux_reponse}%`} />
        </div>
      )}

      {bizStats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatCard
            label="CA signé"
            value={bizStats.ca.total > 0 ? `${bizStats.ca.total.toLocaleString("fr-FR")} €` : "—"}
            accent="text-emerald-600"
            sub={bizStats.ca.count > 0 ? `${bizStats.ca.count} client(s) · moy. ${bizStats.ca.moyen} €` : "Aucun client signé"}
          />
          <StatCard label="Clients gagnés" value={bizStats.entonnoir.gagnes} accent="text-emerald-600" />
          <StatCard
            label="Taux signature"
            value={bizStats.entonnoir.rdv > 0 ? `${bizStats.taux_signature}%` : "—"}
            sub={bizStats.entonnoir.rdv > 0 ? `sur ${bizStats.entonnoir.rdv} RDV` : "Aucun RDV encore"}
          />
          <div className="bg-white border border-slate-200 p-5 rounded-sm">
            <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-3 flex items-center gap-1.5">
              <TrendingUp size={13} /> Entonnoir
            </div>
            <div className="space-y-1.5 text-xs text-slate-600">
              {[
                ["Contactés", bizStats.entonnoir.contactes],
                ["Ont répondu", bizStats.entonnoir.repondus],
                ["RDV pris", bizStats.entonnoir.rdv],
                ["Signés", bizStats.entonnoir.gagnes],
              ].map(([label, val]) => (
                <div key={label} className="flex items-center justify-between">
                  <span>{label}</span>
                  <span className="font-mono font-semibold text-[#111111]">{val}</span>
                </div>
              ))}
            </div>
          </div>
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
            {items.map((item) => {
              const p = item.prospect;
              return (
                <li key={p.id} data-testid="queue-row" className="px-5 py-4 hover:bg-slate-50 transition-colors duration-150">
                  <div className="flex items-center gap-4">
                    <div className="w-12 text-center shrink-0">
                      <div className={`font-mono font-bold text-lg tabular-nums ${p.score_conversion >= 80 ? "text-amber-600" : p.score_conversion >= 60 ? "text-orange-500" : p.score_conversion >= 30 ? "text-blue-600" : "text-slate-500"}`}>
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
                        {p.label_vendabilite && (
                          <Badge variant="outline" className="rounded-sm text-[11px] bg-amber-50 text-amber-800 border-amber-200" title={p.raisons_vendabilite?.join(" · ")}>
                            {p.label_vendabilite}
                          </Badge>
                        )}
                        <span className="text-xs text-slate-400 font-mono">
                          étape {item.etape}/{item.total_etapes} · {item.canal}
                        </span>
                        {item.canal === "linkedin" && (
                          <Badge data-testid="badge-linkedin-warning" variant="outline" className="rounded-sm text-[11px] bg-amber-50 text-amber-700 border-amber-200">
                            <Warning size={11} weight="fill" className="mr-1" /> LinkedIn seul — hors cible ?
                          </Badge>
                        )}
                        {item.accroche_saison && (
                          <Badge data-testid="badge-saison" variant="outline" className="rounded-sm text-[11px] bg-emerald-50 text-emerald-700 border-emerald-200" title={item.accroche_saison}>
                            <Leaf size={11} weight="fill" className="mr-1" /> Saison
                          </Badge>
                        )}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5 truncate">
                        {p.metier} · {p.ville} {p.telephone && `· ${p.telephone}`}
                        {p.signal_principal && ` · ⚡ ${p.signal_principal}`}
                      </div>
                      {p.pitch_vendabilite && (
                        <div className="text-xs text-amber-700 mt-0.5 italic truncate">💡 {p.pitch_vendabilite}</div>
                      )}
                      <div className="text-xs text-slate-400 mt-1 line-clamp-1 italic">"{item.message}"</div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">
                      {item.canal === "whatsapp" && (
                        <Button data-testid="btn-whatsapp-send" size="sm" className="bg-[#25D366] hover:bg-[#1DA851] text-white rounded-sm h-8" onClick={() => openWhatsApp(item)} disabled={!item.wa_link}>
                          <WhatsappLogo size={16} weight="fill" />
                        </Button>
                      )}
                      {item.canal === "linkedin" && (
                        <Button data-testid="btn-linkedin-open" size="sm" className="bg-[#0A66C2] hover:bg-[#004182] text-white rounded-sm h-8" onClick={() => openLinkedIn(item)}>
                          <LinkedinLogo size={16} weight="fill" />
                        </Button>
                      )}
                      {item.canal === "telephone" && (
                        <Button data-testid="btn-telephone-call" size="sm" className="bg-[#111111] hover:bg-slate-800 text-white rounded-sm h-8" onClick={() => (window.location.href = `tel:${p.telephone}`)}>
                          <Phone size={16} weight="fill" />
                        </Button>
                      )}
                      <Button data-testid="btn-mark-sent" size="sm" variant="outline" className="rounded-sm h-8 text-emerald-700 border-emerald-300 hover:bg-emerald-50" onClick={() => doAction(p.id, "envoye", "Marqué envoyé — prochaine relance planifiée")}>
                        <CheckCircle size={16} weight="bold" />
                      </Button>
                      <Button data-testid="btn-gagne" size="sm" variant="outline" className="rounded-sm h-8 text-emerald-700 border-emerald-300 hover:bg-emerald-50 text-xs px-2" onClick={() => setGagneItem(item)} title="Marquer gagné + saisir le CA">
                        🎉
                      </Button>
                      <Button data-testid="btn-rappel" size="sm" variant="outline" className="rounded-sm h-8 text-[#002FA7] border-blue-200 hover:bg-blue-50" onClick={() => setRappelItem(item)} title="Programmer un rappel">
                        <Bell size={15} />
                      </Button>
                      <Button data-testid="btn-perdu" size="sm" variant="outline" className="rounded-sm h-8 text-slate-400 hover:text-red-500 hover:border-red-200 text-xs" onClick={() => setPerduItem(item)} title="Marquer perdu / raison du refus">
                        <X size={14} />
                      </Button>
                      <Button data-testid="btn-skip" size="sm" variant="ghost" className="rounded-sm h-8 text-slate-400" onClick={() => doAction(p.id, "skip", "Reporté à demain")} title="Reporter à demain">
                        <ArrowBendUpRight size={16} />
                      </Button>
                      <Button data-testid="btn-view-prospect" size="sm" variant="ghost" className="rounded-sm h-8" onClick={() => setOpenId(p.id)} title="Détails">
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
