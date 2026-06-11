import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { MagnifyingGlass, Trash, DownloadSimple, WhatsappLogo, LinkedinLogo, EnvelopeSimple, Phone, MagicWand } from "@phosphor-icons/react";
import api, { NIVEAU_STYLES, PROFIL_LABELS, STATUT_LABELS, STATUT_STYLES } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import ProspectSheet from "@/components/ProspectSheet";

const ALL = "__all__";

const CANAL_ICONS = {
  email: <EnvelopeSimple size={15} className="text-slate-700" />,
  whatsapp: <WhatsappLogo size={15} className="text-[#25D366]" />,
  linkedin: <LinkedinLogo size={15} className="text-[#0A66C2]" />,
  telephone: <Phone size={15} className="text-slate-700" />,
};

export default function Prospects() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [statut, setStatut] = useState(ALL);
  const [niveau, setNiveau] = useState(ALL);
  const [profil, setProfil] = useState(ALL);
  const [openId, setOpenId] = useState(null);

  const load = useCallback(async () => {
    const params = {
      q,
      statut: statut === ALL ? "" : statut,
      niveau: niveau === ALL ? "" : niveau,
      profil: profil === ALL ? "" : profil,
      limit: 200,
    };
    const res = await api.get("/prospects", { params });
    setItems(res.data.items);
    setTotal(res.data.total);
  }, [q, statut, niveau, profil]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const remove = async (e, id) => {
    e.stopPropagation();
    if (!window.confirm("Supprimer ce prospect ?")) return;
    await api.delete(`/prospects/${id}`);
    toast.success("Prospect supprimé");
    load();
  };

  const [enrichJob, setEnrichJob] = useState(null);

  const enrichEmails = async () => {
    const res = await api.post("/prospects/enrich-emails");
    setEnrichJob(res.data);
    toast.info("Recherche d'emails lancée sur les sites des prospects…");
    const interval = setInterval(async () => {
      const j = (await api.get(`/scrape/jobs/${res.data.id}`)).data;
      setEnrichJob(j);
      if (["termine", "erreur"].includes(j.statut)) {
        clearInterval(interval);
        setEnrichJob(null);
        if (j.statut === "termine") {
          toast.success(`${j.trouves} email(s) trouvé(s) sur ${j.total} sites visités`);
        } else {
          toast.error("La recherche d'emails a échoué");
        }
        load();
      }
    }, 2000);
  };

  const exportExcel = () => {
    const params = new URLSearchParams({
      q,
      statut: statut === ALL ? "" : statut,
      niveau: niveau === ALL ? "" : niveau,
      profil: profil === ALL ? "" : profil,
    });
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/export/prospects?${params}`, "_blank");
    toast.success("Export Excel en cours de téléchargement");
  };

  return (
    <div className="p-8 fade-up">
      <div className="flex items-end justify-between mb-6">
        <div>
          <h1 className="text-4xl tracking-tighter font-bold text-[#111111]">Prospects</h1>
          <p className="text-sm text-slate-500 mt-1">{total} prospects en base</p>
        </div>
        <div className="flex gap-2">
          <Button
            data-testid="btn-enrich-emails"
            onClick={enrichEmails}
            disabled={!!enrichJob}
            variant="outline"
            className="rounded-sm"
            title="Visite les sites des prospects sans email pour y trouver une adresse"
          >
            <MagicWand size={16} className="mr-2" />
            {enrichJob ? `Recherche… ${enrichJob.traites ?? 0}/${enrichJob.total ?? "?"}` : "Trouver les emails manquants"}
          </Button>
          <Button
            data-testid="btn-export-excel"
            onClick={exportExcel}
            variant="outline"
            className="rounded-sm"
          >
            <DownloadSimple size={16} className="mr-2" /> Exporter Excel
          </Button>
        </div>
      </div>

      <div className="flex gap-3 mb-4 flex-wrap">
        <div className="relative">
          <MagnifyingGlass size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input
            data-testid="input-search-prospects"
            placeholder="Rechercher (nom, ville, tel…)"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9 w-64 rounded-sm bg-white"
          />
        </div>
        <Select value={statut} onValueChange={setStatut}>
          <SelectTrigger data-testid="filter-statut" className="w-44 rounded-sm bg-white">
            <SelectValue placeholder="Statut" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Tous les statuts</SelectItem>
            {Object.entries(STATUT_LABELS).map(([k, v]) => (
              <SelectItem key={k} value={k}>{v}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={niveau} onValueChange={setNiveau}>
          <SelectTrigger data-testid="filter-niveau" className="w-40 rounded-sm bg-white">
            <SelectValue placeholder="Niveau" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Tous niveaux</SelectItem>
            {["Très chaud", "Chaud", "Tiède", "Froid"].map((n) => (
              <SelectItem key={n} value={n}>{n}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={profil} onValueChange={setProfil}>
          <SelectTrigger data-testid="filter-profil" className="w-40 rounded-sm bg-white">
            <SelectValue placeholder="Profil" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Tous profils</SelectItem>
            {Object.entries(PROFIL_LABELS).map(([k, v]) => (
              <SelectItem key={k} value={k}>{v}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="bg-white border border-slate-200 rounded-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wider text-slate-500">
              <th className="px-4 py-3 font-semibold">Score</th>
              <th className="px-4 py-3 font-semibold">Entreprise</th>
              <th className="px-4 py-3 font-semibold">Métier / Ville</th>
              <th className="px-4 py-3 font-semibold">Site</th>
              <th className="px-4 py-3 font-semibold">Profil</th>
              <th className="px-4 py-3 font-semibold">Canal</th>
              <th className="px-4 py-3 font-semibold">Statut</th>
              <th className="px-4 py-3 font-semibold">Séquence</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr
                key={p.id}
                data-testid="table-prospects-row"
                onClick={() => setOpenId(p.id)}
                className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer transition-colors duration-150"
              >
                <td className="px-4 py-2.5">
                  <Badge variant="outline" className={`rounded-sm tabular-nums ${NIVEAU_STYLES[p.niveau_conversion] || ""}`}>
                    {p.score_conversion}
                  </Badge>
                </td>
                <td className="px-4 py-2.5 font-medium text-[#111111] max-w-56 truncate">{p.entreprise}</td>
                <td className="px-4 py-2.5 text-slate-600">{p.metier} · {p.ville}</td>
                <td className="px-4 py-2.5 text-slate-600 tabular-nums">
                  {p.site_web && p.site_web !== "Pas de site" ? `${p.note_site}/100` : "—"}
                </td>
                <td className="px-4 py-2.5 text-slate-600">{PROFIL_LABELS[p.profil] || p.profil}</td>
                <td className="px-4 py-2.5" data-testid="cell-canal" title={p.canal_contact}>
                  {CANAL_ICONS[p.canal_contact] || "—"}
                </td>
                <td className="px-4 py-2.5">
                  <Badge variant="outline" className={`rounded-sm text-[11px] ${STATUT_STYLES[p.statut] || ""}`}>
                    {STATUT_LABELS[p.statut] || p.statut}
                  </Badge>
                </td>
                <td className="px-4 py-2.5 font-mono text-xs" data-testid="cell-sequence">
                  {p.statut === "a_contacter" && p.etape_relance > 1 ? (
                    <span className="text-emerald-700 font-semibold">en cours · {p.etape_relance}/4</span>
                  ) : (
                    <span className="text-slate-500">{p.etape_relance}/4</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <Button
                    data-testid="btn-delete-prospect"
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0 text-slate-300 hover:text-red-500"
                    onClick={(e) => remove(e, p.id)}
                  >
                    <Trash size={14} />
                  </Button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-12 text-center text-slate-400">
                  Aucun prospect — lancez le scraper ou importez un fichier.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <ProspectSheet prospectId={openId} onClose={() => setOpenId(null)} onChanged={load} />
    </div>
  );
}
