import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Play, Database } from "@phosphor-icons/react";
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

export default function Scraper() {
  const [form, setForm] = useState({
    metier: "plombier", ville: "", departement: "", limite: 20, source: "gouv", auditer: true,
  });
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

  const start = async () => {
    if (!form.ville.trim()) {
      toast.error("Indiquez une ville");
      return;
    }
    const res = await api.post("/scrape", { ...form, limite: Number(form.limite) || 20 });
    setJob(res.data);
    poll(res.data.id);
  };

  const running = job && !["termine", "erreur"].includes(job.statut);

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
            <label className="text-xs font-medium text-slate-600 mb-1 block">Métier</label>
            <Select value={form.metier} onValueChange={(v) => setForm({ ...form, metier: v })}>
              <SelectTrigger data-testid="select-metier" className="rounded-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {METIERS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">Ville</label>
            <Input data-testid="input-ville" placeholder="Lyon" value={form.ville}
              onChange={(e) => setForm({ ...form, ville: e.target.value })} className="rounded-sm" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Département</label>
              <Input data-testid="input-departement" placeholder="69 (optionnel)" value={form.departement}
                onChange={(e) => setForm({ ...form, departement: e.target.value })} className="rounded-sm" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Limite</label>
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
            {running ? "Scraping en cours…" : "Lancer le scraping"}
          </Button>
        </div>

        <div className="lg:col-span-2 space-y-6">
          {job && (
            <div className="bg-white border border-slate-200 p-6 rounded-sm">
              <div className="flex items-center justify-between mb-3">
                <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500">
                  Job en cours — {job.params?.metier} à {job.params?.ville}
                </div>
                <span className="font-mono text-sm tabular-nums text-[#002FA7] font-semibold">{job.progress}%</span>
              </div>
              <div className="h-2 bg-slate-100 w-full mb-4">
                <div className="h-2 bg-[#002FA7] transition-all duration-500" style={{ width: `${job.progress}%` }} />
              </div>
              <div className="grid grid-cols-4 gap-3 mb-4 text-center">
                {[["Découverts", job.total], ["Traités", job.traites], ["Ajoutés", job.ajoutes], ["Doublons", job.doublons]].map(([l, v]) => (
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
                      <span className="font-medium">{j.params?.metier}</span>
                      <span className="text-slate-500"> · {j.params?.ville} · {j.params?.source}</span>
                      <div className="text-xs text-slate-400 font-mono">
                        {new Date(j.created_at).toLocaleString("fr-FR")}
                      </div>
                    </div>
                    <div className="text-right">
                      <span className={`text-xs font-semibold ${j.statut === "termine" ? "text-emerald-600" : j.statut === "erreur" ? "text-red-500" : "text-[#002FA7]"}`}>
                        {j.statut}
                      </span>
                      <div className="text-xs text-slate-500 tabular-nums">{j.ajoutes} ajoutés · {j.doublons} doublons</div>
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
