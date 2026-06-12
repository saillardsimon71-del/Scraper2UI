import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  WhatsappLogo,
  LinkedinLogo,
  Sparkle,
  Copy,
  Globe,
  Phone,
  EnvelopeSimple,
  CheckCircle,
  CalendarCheck,
  Prohibit,
  ArrowCounterClockwise,
  CaretRight,
  Bell,
  CurrencyEur,
  Trophy,
  X,
} from "@phosphor-icons/react";
import api, { NIVEAU_STYLES, PROFIL_LABELS, STATUT_LABELS, STATUT_STYLES } from "@/lib/api";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";

export default function ProspectSheet({ prospectId, onClose, onChanged }) {
  const [data, setData] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [miniAudit, setMiniAudit] = useState("");
  const [auditWaLink, setAuditWaLink] = useState("");
  const [draft, setDraft] = useState("");
  const [openHist, setOpenHist] = useState(null);
  const [showRappel, setShowRappel] = useState(false);
  const [showGagne, setShowGagne] = useState(false);
  const [showPerdu, setShowPerdu] = useState(false);
  const [rappelJours, setRappelJours] = useState(7);
  const [caContrat, setCaContrat] = useState("");
  const [raisonRefus, setRaisonRefus] = useState("");

  const RAISONS_SUGGESTIONS = ["Trop cher", "Déjà quelqu'un", "Pas intéressé", "Rappeler plus tard", "A déjà un site récent", "Arrête l'activité"];

  const load = useCallback(async () => {
    if (!prospectId) return;
    try {
      const res = await api.get(`/prospects/${prospectId}`);
      setData(res.data);
      setDraft(res.data.message);
      setMiniAudit(res.data.prospect.mini_audit || "");
    } catch {
      toast.error("Prospect introuvable");
    }
  }, [prospectId]);

  useEffect(() => {
    setData(null);
    load();
  }, [load]);

  if (!prospectId) return null;
  const p = data?.prospect;

  const doAction = async (type, label) => {
    await api.post(`/prospects/${prospectId}/action`, { type });
    toast.success(label);
    load();
    onChanged?.();
  };

  const doActionGagne = async () => {
    await api.post(`/prospects/${prospectId}/action`, {
      type: "gagne",
      ca_contrat: caContrat ? parseFloat(caContrat) : null,
    });
    toast.success(`Client gagné 🎉${caContrat ? ` — ${caContrat} €` : ""}`);
    setShowGagne(false);
    load();
    onChanged?.();
  };

  const doActionPerdu = async () => {
    await api.post(`/prospects/${prospectId}/action`, {
      type: "perdu",
      raison_refus: raisonRefus || "",
    });
    toast.success("Marqué perdu");
    setShowPerdu(false);
    load();
    onChanged?.();
  };

  const doActionRappel = async () => {
    await api.post(`/prospects/${prospectId}/action`, {
      type: "rappel",
      rappel_dans_jours: rappelJours,
    });
    toast.success(`Rappel programmé dans ${rappelJours} jour(s)`);
    setShowRappel(false);
    load();
    onChanged?.();
  };

  const improveAI = async () => {
    setAiLoading(true);
    try {
      const res = await api.post("/ai/improve", {
        message: draft,
        prospect_id: prospectId,
        canal: data.canal,
      });
      setDraft(res.data.message);
      toast.success("Message amélioré par l'IA");
    } catch {
      toast.error("Erreur IA — réessayez");
    } finally {
      setAiLoading(false);
    }
  };

  const generateMiniAudit = async () => {
    setAuditLoading(true);
    try {
      const res = await api.post("/ai/mini-audit", { prospect_id: prospectId });
      setMiniAudit(res.data.mini_audit);
      setAuditWaLink(res.data.wa_link || "");
      toast.success("Mini-audit généré — prêt à envoyer");
    } catch {
      toast.error("Erreur IA — réessayez");
    } finally {
      setAuditLoading(false);
    }
  };

  const saveDraft = async () => {
    await api.patch(`/prospects/${prospectId}`, { message_personnalise: draft });
    toast.success("Message personnalisé enregistré pour ce prospect");
    onChanged?.();
  };

  const copy = async (text) => {
    await navigator.clipboard.writeText(text);
    toast.success("Copié");
  };

  let signaux = {};
  try {
    signaux = JSON.parse(p?.signaux_conversion || "{}");
  } catch {
    /* ignore */
  }
  const signauxActifs = Object.entries(signaux).filter(([, v]) => v).map(([k]) => k.replaceAll("_", " "));

  return (
    <Sheet open={!!prospectId} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-[520px] sm:max-w-[520px] overflow-y-auto rounded-none p-0">
        {!p ? (
          <div className="p-8 text-sm text-slate-400">
            <SheetTitle className="sr-only">Chargement du prospect</SheetTitle>
            Chargement…
          </div>
        ) : (
          <div>
            <SheetHeader className="px-6 pt-6 pb-4 border-b border-slate-200">
              <SheetTitle className="font-heading text-2xl tracking-tight text-[#111111]">
                {p.entreprise}
              </SheetTitle>
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline" className={`rounded-sm ${NIVEAU_STYLES[p.niveau_conversion] || ""}`}>
                  {p.niveau_conversion} · {p.score_conversion}/100
                </Badge>
                <Badge variant="outline" className="rounded-sm">{PROFIL_LABELS[p.profil]}</Badge>
                <Badge variant="outline" className={`rounded-sm ${STATUT_STYLES[p.statut] || ""}`}>
                  {STATUT_LABELS[p.statut]}
                </Badge>
                {p.variante_ab && (
                  <Badge data-testid="badge-variante-ab" variant="outline" className="rounded-sm bg-slate-50 text-slate-600" title="Variante d'objet email assignée (A/B testing)">
                    Objet {p.variante_ab}
                  </Badge>
                )}
              </div>
            </SheetHeader>

            <div className="px-6 py-5 space-y-6">
              <div className="space-y-1.5 text-sm">
                <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">Contact</div>
                <div className="flex items-center gap-2 text-slate-700">
                  <Phone size={14} /> {p.telephone || <span className="text-slate-400">non renseigné</span>}
                  {p.telephone && (
                    <button onClick={() => copy(p.telephone)} className="text-slate-400 hover:text-slate-700">
                      <Copy size={13} />
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-2 text-slate-700">
                  <EnvelopeSimple size={14} /> {p.email || <span className="text-slate-400">non renseigné</span>}
                </div>
                <div className="flex items-center gap-2 text-slate-700">
                  <Globe size={14} />
                  {p.site_web && p.site_web !== "Pas de site" ? (
                    <a href={p.site_web} target="_blank" rel="noreferrer" className="text-[#002FA7] hover:underline truncate">
                      {p.site_web}
                    </a>
                  ) : (
                    <span className="text-slate-400">Pas de site</span>
                  )}
                </div>
                <div className="text-slate-500 text-xs">{p.metier} · {p.ville} {p.code_postal} · source : {p.source}</div>
              </div>

              <div>
                <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">
                  Audit site — {p.note_site}/100
                </div>
                <div className="h-1.5 bg-slate-100 w-full">
                  <div
                    className={`h-1.5 transition-all ${p.note_site < 50 ? "bg-red-400" : p.note_site < 80 ? "bg-amber-400" : "bg-emerald-500"}`}
                    style={{ width: `${p.note_site}%` }}
                  />
                </div>
                {p.opportunites && (
                  <p className="text-xs text-slate-600 mt-2 leading-relaxed">{p.opportunites}</p>
                )}
                {signauxActifs.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {signauxActifs.map((s) => (
                      <span key={s} className="text-[11px] bg-amber-50 text-amber-800 border border-amber-200 px-1.5 py-0.5 rounded-sm">
                        ⚡ {s}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500">
                    Message — étape {data.etape}/{data.total_etapes} · {data.canal}
                  </div>
                  <Button
                    data-testid="btn-ai-improve-message"
                    size="sm"
                    onClick={improveAI}
                    disabled={aiLoading}
                    className="bg-[#111111] hover:bg-slate-800 text-white rounded-sm h-7 text-xs"
                  >
                    <Sparkle size={13} weight="fill" className="mr-1" />
                    {aiLoading ? "IA en cours…" : "Améliorer avec l'IA"}
                  </Button>
                </div>
                <Textarea
                  data-testid="textarea-message-draft"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={5}
                  className="rounded-sm text-sm"
                />
                <div className="flex gap-2 mt-2">
                  <Button data-testid="btn-save-draft" size="sm" variant="outline" className="rounded-sm h-8 text-xs" onClick={saveDraft}>
                    Enregistrer pour ce prospect
                  </Button>
                  <Button size="sm" variant="outline" className="rounded-sm h-8 text-xs" onClick={() => copy(draft)}>
                    <Copy size={13} className="mr-1" /> Copier
                  </Button>
                </div>
                <div className="flex gap-2 mt-3">
                  {data.canal === "whatsapp" && data.wa_link && (
                    <a
                      href={(() => { try { const u = new URL(data.wa_link); u.searchParams.set("text", draft); return u.toString(); } catch { return data.wa_link; } })()}
                      target="_blank" rel="noreferrer" className="flex-1"
                    >
                      <Button data-testid="sheet-btn-whatsapp" className="w-full bg-[#25D366] hover:bg-[#1DA851] text-white rounded-sm h-9">
                        <WhatsappLogo size={16} weight="fill" className="mr-2" /> WhatsApp
                      </Button>
                    </a>
                  )}
                  {data.canal === "linkedin" && (
                    <a href={data.linkedin_link} target="_blank" rel="noreferrer" className="flex-1" onClick={() => copy(draft)}>
                      <Button data-testid="sheet-btn-linkedin" className="w-full bg-[#0A66C2] hover:bg-[#004182] text-white rounded-sm h-9">
                        <LinkedinLogo size={16} weight="fill" className="mr-2" /> LinkedIn
                      </Button>
                    </a>
                  )}
                  {data.canal === "telephone" && p.telephone && (
                    <a href={`tel:${p.telephone}`} className="flex-1">
                      <Button data-testid="sheet-btn-telephone" className="w-full bg-[#111111] hover:bg-slate-800 text-white rounded-sm h-9">
                        <Phone size={16} weight="fill" className="mr-2" /> Appeler {p.telephone}
                      </Button>
                    </a>
                  )}
                  {data.canal === "email" && (
                    <div data-testid="sheet-canal-email-note" className="flex-1 flex items-center gap-2 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-sm px-3 py-2">
                      <EnvelopeSimple size={15} className="shrink-0 text-slate-700" />
                      Séquence email — envois gérés automatiquement par le pilote automatique.
                    </div>
                  )}
                </div>
              </div>

              <div className="border border-slate-200 bg-slate-50/60 rounded-sm p-4">
                <div className="flex items-center justify-between mb-1">
                  <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500">
                    Mini-audit IA
                  </div>
                  <Button
                    data-testid="btn-generate-mini-audit"
                    size="sm"
                    onClick={generateMiniAudit}
                    disabled={auditLoading}
                    className="bg-[#111111] hover:bg-slate-800 text-white rounded-sm h-7 text-xs"
                  >
                    <Sparkle size={13} weight="fill" className="mr-1" />
                    {auditLoading ? "Génération…" : miniAudit ? "Régénérer" : "Générer le mini-audit"}
                  </Button>
                </div>
                <p className="text-[11px] text-slate-400 mb-2">
                  Version client : sans note, sans jargon — parfait en relance pour prouver votre valeur.
                </p>
                {miniAudit ? (
                  <>
                    <div data-testid="mini-audit-text" className="text-sm text-slate-700 whitespace-pre-line bg-white border border-slate-200 rounded-sm p-3 leading-relaxed">
                      {miniAudit}
                    </div>
                    <div className="flex gap-2 mt-2">
                      <Button size="sm" variant="outline" className="rounded-sm h-8 text-xs" onClick={() => copy(miniAudit)}>
                        <Copy size={13} className="mr-1" /> Copier
                      </Button>
                      {p.telephone && (
                        <a
                          href={auditWaLink || `https://wa.me/${p.telephone.replace(/[^\d]/g, "").replace(/^0/, "33")}?text=${encodeURIComponent(miniAudit)}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <Button data-testid="btn-mini-audit-whatsapp" size="sm" className="bg-[#25D366] hover:bg-[#1DA851] text-white rounded-sm h-8 text-xs">
                            <WhatsappLogo size={13} weight="fill" className="mr-1" /> Envoyer sur WhatsApp
                          </Button>
                        </a>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="text-xs text-slate-400 italic">Pas encore généré pour ce prospect.</div>
                )}
              </div>

              {data.sequence && (
                <div>
                  <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">
                    Séquence complète ({PROFIL_LABELS[p.profil]})
                  </div>
                  {p.plan_canaux?.length > 0 && (
                    <div data-testid="plan-canaux" className="text-xs text-slate-500 font-mono mb-2">
                      Plan multi-canal : {p.plan_canaux.join(" → ")}
                    </div>
                  )}
                  <div className="space-y-2">
                    {data.sequence.map((s) => (
                      <div
                        key={s.etape}
                        className={`border p-3 rounded-sm text-xs ${s.etape === data.etape && p.statut === "a_contacter" ? "border-[#002FA7] bg-blue-50/50" : "border-slate-200"}`}
                      >
                        <div className="font-semibold text-slate-700 mb-1">
                          Étape {s.etape} · {s.canal} · {s.delai_jours === 0 ? "J0" : `J+${s.delai_jours} après précédent`}
                        </div>
                        {s.objet && (
                          <div className="text-slate-400 mb-1">Objet : <span className="text-slate-600">{s.objet}</span></div>
                        )}
                        <p className="text-slate-500 leading-relaxed">{s.message}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">Statut</div>

                {/* Vendabilité */}
                {p.label_vendabilite && (
                  <div className="mb-3 bg-amber-50 border border-amber-200 rounded-sm p-3">
                    <div className="text-xs font-semibold text-amber-800 mb-1">Argument de vente : {p.label_vendabilite}</div>
                    {p.pitch_vendabilite && <p className="text-xs text-amber-700 italic">{p.pitch_vendabilite}</p>}
                    {p.raisons_vendabilite?.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {p.raisons_vendabilite.map((r) => (
                          <span key={r} className="text-[10px] bg-amber-100 text-amber-800 border border-amber-200 px-1.5 py-0.5 rounded-sm">⚡ {r}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* CA et raison refus si dispo */}
                {p.ca_contrat > 0 && (
                  <div className="mb-3 flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-sm px-3 py-2">
                    <Trophy size={14} weight="fill" />
                    Client signé — <span className="font-bold">{p.ca_contrat.toLocaleString("fr-FR")} €</span>
                  </div>
                )}
                {p.raison_refus && (
                  <div className="mb-3 text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-sm px-3 py-2">
                    Raison du refus : <span className="font-medium text-slate-700">{p.raison_refus}</span>
                  </div>
                )}

                {/* Boutons d'action */}
                {!showGagne && !showPerdu && !showRappel && (
                  <div className="grid grid-cols-2 gap-2">
                    <Button data-testid="btn-action-envoye" size="sm" variant="outline" className="rounded-sm text-emerald-700 border-emerald-300"
                      onClick={() => doAction("envoye", "Envoyé — relance planifiée")}>
                      <CheckCircle size={14} className="mr-1.5" /> Marquer envoyé
                    </Button>
                    <Button data-testid="btn-action-repondu" size="sm" variant="outline" className="rounded-sm"
                      onClick={() => doAction("repondu", "Marqué répondu")}>
                      💬 A répondu
                    </Button>
                    <Button data-testid="btn-action-rdv" size="sm" variant="outline" className="rounded-sm text-violet-700 border-violet-300"
                      onClick={() => doAction("rdv", "RDV pris 🎉")}>
                      <CalendarCheck size={14} className="mr-1.5" /> RDV pris
                    </Button>
                    <Button data-testid="btn-action-gagne" size="sm" variant="outline" className="rounded-sm text-emerald-700 border-emerald-300"
                      onClick={() => setShowGagne(true)}>
                      <Trophy size={14} className="mr-1.5" /> Client gagné 🎉
                    </Button>
                    <Button data-testid="btn-action-rappel" size="sm" variant="outline" className="rounded-sm text-[#002FA7] border-blue-200"
                      onClick={() => setShowRappel(true)}>
                      <Bell size={14} className="mr-1.5" /> Rappeler dans…
                    </Button>
                    <Button data-testid="btn-action-perdu" size="sm" variant="outline" className="rounded-sm text-red-600 border-red-200"
                      onClick={() => setShowPerdu(true)}>
                      <Prohibit size={14} className="mr-1.5" /> Perdu / Refus
                    </Button>
                    {p.statut !== "a_contacter" && (
                      <Button data-testid="btn-action-reactiver" size="sm" variant="outline" className="rounded-sm col-span-2"
                        onClick={() => doAction("reactiver", "Prospect réactivé en étape 1")}>
                        <ArrowCounterClockwise size={14} className="mr-1.5" /> Réactiver la séquence
                      </Button>
                    )}
                  </div>
                )}

                {/* Modale inline : Gagné */}
                {showGagne && (
                  <div className="border border-emerald-200 bg-emerald-50 rounded-sm p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold text-emerald-800">🎉 Client gagné !</div>
                      <button onClick={() => setShowGagne(false)}><X size={14} className="text-slate-400" /></button>
                    </div>
                    <div>
                      <label className="text-xs text-slate-500 block mb-1">Montant du contrat (€)</label>
                      <div className="relative">
                        <CurrencyEur size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                        <input type="number" value={caContrat} onChange={e => setCaContrat(e.target.value)} placeholder="300"
                          className="w-full border border-emerald-200 rounded-sm pl-8 pr-3 py-2 text-sm outline-none focus:border-emerald-500 bg-white" />
                      </div>
                    </div>
                    <Button size="sm" className="w-full bg-emerald-600 hover:bg-emerald-700 text-white rounded-sm" onClick={doActionGagne}>
                      Confirmer le client gagné
                    </Button>
                  </div>
                )}

                {/* Modale inline : Rappel */}
                {showRappel && (
                  <div className="border border-blue-200 bg-blue-50 rounded-sm p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold text-blue-800">Rappeler dans…</div>
                      <button onClick={() => setShowRappel(false)}><X size={14} className="text-slate-400" /></button>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {[1, 3, 7, 14, 30, 60].map((j) => (
                        <button key={j} onClick={() => setRappelJours(j)}
                          className={`px-2.5 py-1 text-xs rounded-sm border transition-colors ${rappelJours === j ? "bg-[#002FA7] text-white border-[#002FA7]" : "border-blue-200 bg-white text-blue-700 hover:border-[#002FA7]"}`}>
                          {j === 1 ? "Demain" : j < 7 ? `${j}j` : j === 7 ? "1 sem" : j === 14 ? "2 sem" : j === 30 ? "1 mois" : "2 mois"}
                        </button>
                      ))}
                    </div>
                    <Button size="sm" className="w-full bg-[#002FA7] hover:bg-[#001f7a] text-white rounded-sm" onClick={doActionRappel}>
                      <Bell size={13} className="mr-1.5" /> Programmer le rappel
                    </Button>
                  </div>
                )}

                {/* Modale inline : Perdu */}
                {showPerdu && (
                  <div className="border border-red-200 bg-red-50 rounded-sm p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold text-red-800">Raison du refus</div>
                      <button onClick={() => setShowPerdu(false)}><X size={14} className="text-slate-400" /></button>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {RAISONS_SUGGESTIONS.map((r) => (
                        <button key={r} onClick={() => setRaisonRefus(r)}
                          className={`px-2.5 py-1 text-xs rounded-sm border transition-colors ${raisonRefus === r ? "bg-red-600 text-white border-red-600" : "border-red-200 bg-white text-red-700 hover:border-red-400"}`}>
                          {r}
                        </button>
                      ))}
                    </div>
                    <input value={raisonRefus} onChange={e => setRaisonRefus(e.target.value)} placeholder="Autre raison…"
                      className="w-full border border-red-200 rounded-sm px-3 py-2 text-sm bg-white outline-none focus:border-red-400" />
                    <Button size="sm" className="w-full bg-red-600 hover:bg-red-700 text-white rounded-sm" onClick={doActionPerdu}>
                      Enregistrer le refus
                    </Button>
                  </div>
                )}
              </div>

              {p.historique?.length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">Historique</div>
                  <div className="space-y-1">
                    {[...p.historique].reverse().map((h, i) => (
                      <div key={i}>
                        <button
                          data-testid="historique-entry"
                          onClick={() => h.message && setOpenHist(openHist === i ? null : i)}
                          className={`w-full text-left text-xs text-slate-500 font-mono flex items-center gap-1.5 ${h.message ? "hover:text-[#002FA7] cursor-pointer" : "cursor-default"}`}
                        >
                          {h.message && (
                            <CaretRight size={11} className={`shrink-0 transition-transform ${openHist === i ? "rotate-90" : ""}`} />
                          )}
                          <span>
                            {new Date(h.date).toLocaleString("fr-FR")} — {h.type}
                            {h.canal ? ` · ${h.canal}` : ""} (étape {h.etape}){h.auto ? " · auto" : ""}
                          </span>
                        </button>
                        {openHist === i && h.message && (
                          <div data-testid="historique-message" className="ml-4 mt-1 mb-2 bg-slate-50 border border-slate-200 rounded-sm p-3 text-xs text-slate-700 whitespace-pre-line leading-relaxed">
                            {h.objet && <div className="font-semibold mb-1.5">Objet : {h.objet}</div>}
                            {h.message}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
