import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CloudArrowUp, ArrowCounterClockwise, Database } from "@phosphor-icons/react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("fr-FR", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function BackupCard() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState(false);

  const refresh = async () => {
    try {
      const res = await api.get("/backup/status");
      setStatus(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, []);

  const dumpNow = async () => {
    setLoading(true);
    try {
      const res = await api.post("/backup/dump");
      toast.success(`Sauvegarde OK — ${res.data.total_docs} documents`);
      await refresh();
    } catch (err) {
      toast.error("Sauvegarde échouée");
    } finally {
      setLoading(false);
    }
  };

  const restore = async () => {
    if (!window.confirm(
      "Restaurer va ÉCRASER la base actuelle avec le contenu du backup. Continuer ?"
    )) return;
    setRestoring(true);
    try {
      const res = await api.post("/backup/restore");
      toast.success(`Restauration OK — ${res.data.total_docs} documents`);
      await refresh();
    } catch (err) {
      toast.error("Restauration échouée");
    } finally {
      setRestoring(false);
    }
  };

  const manifest = status?.manifest;
  const currentDb = status?.current_db || {};
  const files = status?.files || [];

  return (
    <div className="mt-6 bg-white border border-slate-200 rounded-sm p-6">
      <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-3">
        <Database size={14} /> Sauvegarde &amp; restauration
      </div>
      <p className="text-xs text-slate-500 leading-relaxed mb-4">
        Vos données sont exportées en JSON dans <code className="bg-slate-100 px-1 rounded">/app/data/backup</code> toutes
        les 5 minutes. Cliquez sur <strong>"Save to GitHub"</strong> dans l&apos;en-tête Emergent pour pousser le backup
        et le rendre <strong>persistant à 100%</strong> contre les redémarrages du conteneur. Au prochain démarrage si la
        base est vide, la restauration est automatique.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div className="border border-slate-200 rounded-sm p-3">
          <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Base actuelle</div>
          <div className="space-y-1 text-sm">
            {Object.entries(currentDb).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-slate-600">{k}</span>
                <span className="font-mono">{v}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="border border-slate-200 rounded-sm p-3">
          <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Dernier backup</div>
          {manifest ? (
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-600">Date</span>
                <span className="font-mono text-xs">{fmtDate(manifest.last_dump_at)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-600">Documents</span>
                <span className="font-mono">{manifest.total_docs}</span>
              </div>
              {files.length > 0 && (
                <div className="text-[11px] text-slate-400 mt-2">
                  {files.map((f) => (
                    <div key={f.name} className="flex justify-between">
                      <span>{f.name}.json</span>
                      <span>{f.size_kb} ko</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-slate-400 italic">Aucun backup pour le moment.</p>
          )}
        </div>
      </div>

      <div className="flex gap-2 flex-wrap">
        <Button
          data-testid="btn-backup-dump"
          onClick={dumpNow}
          disabled={loading}
          className="bg-[#002FA7] hover:bg-[#00227A] text-white rounded-sm"
        >
          <CloudArrowUp size={16} className="mr-2" />
          {loading ? "Sauvegarde en cours..." : "Sauvegarder maintenant"}
        </Button>
        <Button
          data-testid="btn-backup-restore"
          onClick={restore}
          disabled={restoring || !manifest}
          variant="outline"
          className="rounded-sm"
        >
          <ArrowCounterClockwise size={16} className="mr-2" />
          {restoring ? "Restauration..." : "Restaurer depuis le backup"}
        </Button>
      </div>

      <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-sm">
        <p className="text-[11px] text-amber-900 leading-relaxed">
          <strong>⚠️ Important :</strong> après une session de travail (scraping, envois, réponses), pensez à cliquer
          <strong> "Save to GitHub"</strong> dans Emergent. Sans push Git, le backup local sera perdu si le conteneur
          est recréé.
        </p>
      </div>
    </div>
  );
}
