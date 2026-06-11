import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Play, Database, X, Plus } from "@phosphor-icons/react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const METIERS = [
  "plombier", "electricien", "menuisier", "peintre", "maçon",
  "couvreur", "chauffagiste", "serrurier", "carreleur", "jardinier",
];

function jobLabel(params) {
  if (!params) return "";
  const metiers = params.metiers?.join(", ") || params.metier || "";
  const villes = params.villes?.join(", ") || params.ville || "";
  return `${metiers} à ${villes}`;
}

export default function Scraper() {
  const [form, setForm] = useState({
    metiers: ["plombier"], villes: [], departement: "", limite: 20, source: "gouv", auditer: true,
  });
  const [villeInput, setVilleInput] = useState("");
  const [job, setJob] = useState(null);
  const [jobs, setJobs] = useState([]);
  const pollRef = useRef(null);

  const loadJobs = async () => {
    const res = await api.get("/scrape/jobs");
    setJobs(res.data.jobs);
  };

  useEffect(() => {
    loadJobs();
    return () => clearInterval(pollRef.current);
  }, []);

  const poll = (jobId) => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const res = await api.get(`/scrape/jobs/${jobId}`);
      setJob(res.data);
      if (["termine", "erreur"].includes(res.data.statut)) {
        clearInterval(pollRef.current);
        loadJobs();
        if (res.data.statut === "termine") {
          toast.success(`Scraping terminé : ${res.data.ajoutes} prospects ajoutés`);
        }
      }
    }, 1500);
  };

  const toggleMetier = (m) => {
    setForm((f) => ({
      ...f,
      metiers: f.metiers.includes(m) ? f.metiers.filter((x) => x !== m) : [...f.metiers, m],
    }));
  };

  const addVille = (raw) => {
    const villes = (raw || villeInput)
      .split(/[,;]/)
      .map((v) => v.trim())
      .filter((v) => v && !form.villes.some((x) => x.toLowerCase() === v.toLowerCase()));
    if (villes.length) setForm((f) => ({ ...f, villes: [...f.villes, ...villes] }));
    setVilleInput("");
  };

  const removeVille = (v) => setForm((f) => ({ ...f, villes: f.villes.filter((x) => x !== v) }));

  const start = async () => {
    const villes = [...form.villes];
    const pending = villeInput.trim();
    if (pending && !villes.some((x) => x.toLowerCase() === pending.toLowerCase())) villes.push(pending);
    if (!form.metiers.length) {
      toast.error("Sélectionnez au moins un métier");
      return;
    }
    if (!villes.length) {
      toast.error("Ajoutez au moins une ville");
      return;
    }
    setVilleInput("");
    setForm((f) => ({ ...f, villes }));
    const res = await api.post("/scrape", {
      metiers: form.metiers,
      villes,
      departement: form.departement,
      limite: Number(form.limite) || 20,
      source: form.source,
      auditer: form.auditer,
    });
    setJob(res.data);
    poll(res.data.id);
  };

  const running = job && !["termine", "erreur"].includes(job.statut);
  const combinaisons = form.metiers.length * Math.max(form.villes.length + (villeInput.trim() ? 1 : 0), 0);

  return (
    <div className="p-8 fade-up">
      <h1 className="text-4xl tracking-tighter font-bold text-[#111111]">Scraper</h1>
      <p className="text-sm text-slate-500 mt-1 mb-8">
        Découverte via API Entreprises (gouv.fr) ou OpenStreetMap, enrichissement téléphone, audit du site et scoring automatique.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-white border border-slate-200 p-6 rounded-sm space-y-4">
          <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500">Nouvelle recherche</div>

          <div>
            <label className="text-xs font-medium text-slate-600 mb-1.5 block">
              Métiers <span className="text-slate-400">({form.metiers.length} sélectionné{form.metiers.length > 1 ? "s" : ""})</span>
            </label>
            <div className="flex flex-wrap gap-1.5">
              {METIERS.map((m) => (
                <button
                  key={m}
                  data-testid={`chip-metier-${m}`}
                  onClick={() => toggleMetier(m)}
                  className={`text-xs px-2.5 py-1.5 rounded-sm border transition-colors ${
                    form.metiers.includes(m)
                      ? "bg-[#002FA7] border-[#002FA7] text-white"
                      : "bg-white border-slate-200 text-slate-600 hover:border-[#002FA7]"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600 mb-1.5 block">
              Villes <span className="text-slate-400">(Entrée pour ajouter)</span>
            </label>
            {form.villes.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {form.villes.map((v) => (
                  <span
                    key={v}
                    data-testid={`chip-ville-${v}`}
                    className="inline-flex items-center gap-1 text-xs bg-slate-100 border border-slate-200 px-2 py-1 rounded-sm"
                  >
                    {v}
                    <button onClick={() => removeVille(v)} className="text-slate-400 hover:text-red-500">
                      <X size={11} weight="bold" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex gap-1.5">
              <Input
                data-testid="input-ville"
                placeholder="Lyon, Villeurbanne…"
                value={villeInput}
                onChange={(e) => setVilleInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addVille();
                  }
                }}
                className="rounded-sm"
              />
              <Button
                data-testid="btn-add-ville"
                variant="outline"
                onClick={() => addVille()}
                disabled={!villeInput.trim()}
                className="rounded-sm shrink-0 px-3"
                title="Ajouter la ville"
              >
                <Plus size={14} weight="bold" />
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Département</label>
              <Input data-testid="input-departement" placeholder="69 (optionnel)" value={form.departement}
                onChange={(e) => setForm({ ...form, departement: e.target.value })} className="rounded-sm" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Limite / recherche</label>
              <Input data-testid="input-limite" type="number" min={1} max={100} value={form.limite}
                onChange={(e) => setForm({ ...form, limite: e.target.value })} className="rounded-sm" />
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">Source</label>
            <Select value={form.source} onValueChange={(v) => setForm({ ...form, source: v })}>
              <SelectTrigger data-testid="select-source" className="rounded-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="gouv">API Entreprises (gouv.fr)</SelectItem>
                <SelectItem value="osm">OpenStreetMap</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-[11px] text-slate-400 mt-1">
              OSM fournit souvent téléphone + site web directement. Gouv donne plus de volume (+ SIREN).
            </p>
          </div>

          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-slate-600">Audit des sites + scoring</label>
            <Switch data-testid="switch-auditer" checked={form.auditer}
              onCheckedChange={(v) => setForm({ ...form, auditer: v })} />
          </div>

          <Button data-testid="form-scraper-submit" onClick={start} disabled={running}
            className="w-full bg-[#002FA7] hover:bg-[#00227A] text-white rounded-sm h-10">
            <Play size={16} weight="fill" className="mr-2" />
            {running ? "Scraping en cours…" : combinaisons > 1
              ? `Lancer le scraping (${combinaisons} recherches)`
              : "Lancer le scraping"}
          </Button>
        </div>

        <div className="lg:col-span-2 space-y-6">
          {job && (
            <div className="bg-white border border-slate-200 p-6 rounded-sm">
              <div className="flex items-center justify-between mb-3">
                <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500">
                  Job en cours — {jobLabel(job.params)}
                </div>
                <span className="font-mono text-sm tabular-nums text-[#002FA7] font-semibold">{job.progress}%</span>
              </div>
              <div className="h-2 bg-slate-100 w-full mb-4">
                <div className="h-2 bg-[#002FA7] transition-all duration-500" style={{ width: `${job.progress}%` }} />
              </div>
              <div className="grid grid-cols-5 gap-3 mb-4 text-center">
                {[["Découverts", job.total], ["Traités", job.traites], ["Ajoutés", job.ajoutes], ["Doublons", job.doublons], ["Sans contact", job.sans_contact ?? 0]].map(([l, v]) => (
                  <div key={l} className="border border-slate-200 py-2 rounded-sm">
                    <div className="font-mono font-semibold tabular-nums">{v}</div>
                    <div className="text-[10px] uppercase text-slate-400">{l}</div>
                  </div>
                ))}
              </div>
              <div data-testid="scraper-log-console" className="bg-[#111111] text-emerald-400 font-mono text-xs p-4 rounded-sm max-h-48 overflow-y-auto space-y-1">
                {(job.logs || []).map((l, i) => <div key={i}>{l}</div>)}
                {running && <div className="animate-pulse">▍</div>}
              </div>
            </div>
          )}

          <div className="bg-white border border-slate-200 rounded-sm">
            <div className="px-6 py-4 border-b border-slate-200 text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 flex items-center gap-2">
              <Database size={14} /> Historique des jobs
            </div>
            {jobs.length === 0 ? (
              <div className="p-8 text-center text-sm text-slate-400">Aucun job pour l'instant</div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {jobs.map((j) => (
                  <li key={j.id} className="px-6 py-3 flex items-center justify-between text-sm">
                    <div>
                      <span className="font-medium">{jobLabel(j.params)}</span>
                      <span className="text-slate-500"> · {j.params?.source}</span>
                      <div className="text-xs text-slate-400 font-mono">
                        {new Date(j.created_at).toLocaleString("fr-FR")}
                      </div>
                    </div>
                    <div className="text-right">
                      <span className={`text-xs font-semibold ${j.statut === "termine" ? "text-emerald-600" : j.statut === "erreur" ? "text-red-500" : "text-[#002FA7]"}`}>
                        {j.statut}
                      </span>
                      <div className="text-xs text-slate-500 tabular-nums">{j.ajoutes} ajoutés · {j.doublons} doublons{j.sans_contact ? ` · ${j.sans_contact} sans contact` : ""}</div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
