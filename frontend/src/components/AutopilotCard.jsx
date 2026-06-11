import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { PaperPlaneTilt, Play, Robot } from "@phosphor-icons/react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";

export default function AutopilotCard() {
  const [form, setForm] = useState(null);
  const [status, setStatus] = useState(null);
  const [log, setLog] = useState([]);
  const [running, setRunning] = useState(false);

  const refresh = useCallback(() => {
    api.get("/autopilot/status").then((res) => setStatus(res.data));
    api.get("/autopilot/log?limit=20").then((res) => setLog(res.data.items));
  }, []);

  useEffect(() => {
    api.get("/settings").then((res) =>
      setForm({
        autopilot_actif: res.data.autopilot_actif,
        autopilot_quota_jour: res.data.autopilot_quota_jour,
        autopilot_heure_debut: res.data.autopilot_heure_debut,
        autopilot_heure_fin: res.data.autopilot_heure_fin,
        autopilot_jours_ouvres: res.data.autopilot_jours_ouvres,
      })
    );
    refresh();
  }, [refresh]);

  const save = async (patch) => {
    const next = { ...form, ...patch };
    setForm(next);
    await api.put("/settings", next);
    refresh();
  };

  const toggle = async (checked) => {
    await save({ autopilot_actif: checked });
    toast.success(checked ? "Pilote automatique activé — les emails des séquences partiront tout seuls" : "Pilote automatique désactivé");
  };

  const runNow = async () => {
    setRunning(true);
    try {
      const { data } = await api.post("/autopilot/run");
      if (data.executed) {
        toast.success(`Passage terminé : ${data.envoyes} email(s) envoyé(s)${data.erreurs ? `, ${data.erreurs} erreur(s)` : ""}`);
      } else {
        toast.info(data.raison);
      }
      refresh();
    } catch (e) {
      toast.error("Erreur lors du passage");
    } finally {
      setRunning(false);
    }
  };

  if (!form || !status) return null;

  return (
    <div data-testid="autopilot-card" className="mt-6 bg-white border border-slate-200 rounded-sm p-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] font-semibold text-slate-500">
            <Robot size={14} /> Pilote automatique — emails
          </div>
          <p className="text-xs text-slate-500 mt-2 leading-relaxed max-w-md">
            Envoie automatiquement les étapes <strong>email</strong> des séquences aux prospects dus
            (relances incluses). S'arrête dès qu'un prospect répond ou se désabonne.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold ${form.autopilot_actif ? "text-emerald-600" : "text-slate-400"}`}>
            {form.autopilot_actif ? "ACTIF" : "INACTIF"}
          </span>
          <Switch data-testid="switch-autopilot" checked={form.autopilot_actif} onCheckedChange={toggle} />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Badge data-testid="badge-envoyes-jour" variant="outline" className="rounded-sm bg-slate-50">
          {status.envoyes_aujourdhui}/{status.quota} envoyés aujourd'hui
        </Badge>
        <Badge data-testid="badge-en-attente" variant="outline" className="rounded-sm bg-blue-50 text-blue-700 border-blue-200">
          {status.en_attente} email(s) prêt(s) à partir
        </Badge>
        {form.autopilot_actif && status.raison_pause && (
          <Badge data-testid="badge-raison-pause" variant="outline" className="rounded-sm bg-amber-50 text-amber-800 border-amber-200">
            En pause : {status.raison_pause}
          </Badge>
        )}
      </div>

      <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <label className="text-[11px] font-medium text-slate-600 mb-1 block">Quota / jour</label>
          <Input data-testid="input-quota-jour" type="number" min={1} className="rounded-sm h-9"
            value={form.autopilot_quota_jour}
            onChange={(e) => setForm({ ...form, autopilot_quota_jour: Number(e.target.value) })}
            onBlur={() => save({})} />
        </div>
        <div>
          <label className="text-[11px] font-medium text-slate-600 mb-1 block">Début (h)</label>
          <Input data-testid="input-heure-debut" type="number" min={0} max={23} className="rounded-sm h-9"
            value={form.autopilot_heure_debut}
            onChange={(e) => setForm({ ...form, autopilot_heure_debut: Number(e.target.value) })}
            onBlur={() => save({})} />
        </div>
        <div>
          <label className="text-[11px] font-medium text-slate-600 mb-1 block">Fin (h)</label>
          <Input data-testid="input-heure-fin" type="number" min={1} max={24} className="rounded-sm h-9"
            value={form.autopilot_heure_fin}
            onChange={(e) => setForm({ ...form, autopilot_heure_fin: Number(e.target.value) })}
            onBlur={() => save({})} />
        </div>
        <div className="flex flex-col">
          <label className="text-[11px] font-medium text-slate-600 mb-1 block">Jours ouvrés</label>
          <div className="h-9 flex items-center">
            <Switch data-testid="switch-jours-ouvres" checked={form.autopilot_jours_ouvres}
              onCheckedChange={(c) => save({ autopilot_jours_ouvres: c })} />
          </div>
        </div>
      </div>

      <Button data-testid="btn-run-autopilot" onClick={runNow} disabled={running}
        variant="outline" className="mt-4 rounded-sm border-[#002FA7] text-[#002FA7] hover:bg-[#002FA7] hover:text-white">
        <Play size={15} className="mr-2" weight="bold" />
        {running ? "Envoi en cours…" : "Lancer un passage maintenant"}
      </Button>

      <div className="mt-6 border-t border-slate-100 pt-4">
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-3">
          <PaperPlaneTilt size={14} /> Journal des envois
        </div>
        {log.length === 0 ? (
          <p data-testid="log-vide" className="text-xs text-slate-400">Aucun email envoyé pour le moment.</p>
        ) : (
          <div data-testid="autopilot-log" className="space-y-1.5 max-h-64 overflow-y-auto">
            {log.map((l) => (
              <div key={l.id} className="flex items-center gap-2 text-xs py-1.5 px-2 bg-slate-50 rounded-sm">
                <span className={`shrink-0 w-1.5 h-1.5 rounded-full ${l.statut === "envoye" ? "bg-emerald-500" : "bg-red-500"}`} />
                <span className="text-slate-400 shrink-0">
                  {new Date(l.date).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                </span>
                <span className="font-medium text-slate-700 truncate">{l.entreprise}</span>
                <span className="text-slate-400 truncate">{l.destinataire}</span>
                <span className="text-slate-500 truncate hidden sm:block">« {l.objet} »</span>
                <span className="ml-auto shrink-0 text-slate-400">ét. {l.etape}{l.auto ? " · auto" : ""}</span>
                {l.statut === "erreur" && <span className="shrink-0 text-red-500" title={l.erreur}>échec</span>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
