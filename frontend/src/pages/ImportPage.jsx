import { useRef, useState } from "react";
import { toast } from "sonner";
import { UploadSimple, FileXls, CheckCircle, EnvelopeSimple, ArrowClockwise } from "@phosphor-icons/react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function ImportPage() {
  const inputRef = useRef(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [sgLoading, setSgLoading] = useState(false);
  const [sgPreview, setSgPreview] = useState(null);
  const [sgResult, setSgResult] = useState(null);
  const [sinceDays, setSinceDays] = useState(7);

  const upload = async (file) => {
    if (!file) return;
    setLoading(true);
    setResult(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await api.post("/import", fd);
      setResult(res.data);
      toast.success(`${res.data.importes} prospects importés`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Import impossible");
    } finally {
      setLoading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="p-8 fade-up max-w-3xl">
      <h1 className="text-4xl tracking-tighter font-bold text-[#111111]">Import</h1>
      <p className="text-sm text-slate-500 mt-1 mb-8">
        Importez les fichiers Excel / CSV générés par votre scraper (ex. <span className="font-mono">sortie/artisans.xlsx</span>).
        Les colonnes sont reconnues automatiquement, les doublons ignorés, le score et le profil recalculés si absents.
      </p>

      <div
        data-testid="import-dropzone"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          upload(e.dataTransfer.files?.[0]);
        }}
        className="bg-white border-2 border-dashed border-slate-300 hover:border-[#002FA7] transition-colors duration-150 rounded-sm p-16 text-center cursor-pointer"
      >
        <UploadSimple size={36} className="mx-auto text-slate-400 mb-3" />
        <div className="font-heading font-semibold text-lg">
          {loading ? "Import en cours…" : "Glissez votre fichier ici ou cliquez"}
        </div>
        <div className="text-xs text-slate-400 mt-1">.xlsx, .xls ou .csv</div>
        <input
          ref={inputRef}
          data-testid="import-file-input"
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={(e) => upload(e.target.files?.[0])}
        />
      </div>

      {result && (
        <div className="mt-6 bg-white border border-slate-200 rounded-sm p-6">
          <div className="flex items-center gap-2 text-emerald-700 font-semibold mb-3">
            <CheckCircle size={18} weight="fill" /> Import terminé
          </div>
          <div className="grid grid-cols-4 gap-4 text-center mb-4">
            {[["Importés", result.importes, "text-emerald-600"], ["Doublons ignorés", result.doublons, "text-amber-600"], ["Sans contact", result.sans_contact ?? 0, "text-slate-500"], ["Erreurs", result.erreurs, "text-red-500"]].map(([l, v, c]) => (
              <div key={l} className="border border-slate-200 py-3 rounded-sm">
                <div className={`font-heading text-2xl font-bold tabular-nums ${c}`}>{v}</div>
                <div className="text-[11px] uppercase text-slate-400">{l}</div>
              </div>
            ))}
          </div>
          <div className="text-xs text-slate-500">
            Colonnes reconnues : <span className="font-mono">{result.colonnes_reconnues.join(", ")}</span>
          </div>
        </div>
      )}

      <div className="mt-8 bg-white border border-slate-200 rounded-sm p-6">
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-3">
          <FileXls size={14} /> Colonnes supportées
        </div>
        <p className="text-xs text-slate-500 leading-relaxed">
          <span className="font-mono">nom / entreprise</span> (obligatoire) · métier · ville · code postal · adresse · siren · téléphone · email ·
          site web · linkedin · note site · score conversion · niveau conversion · signal principal · pistes d'amélioration ·
          message whatsapp · message linkedin · source. Les accents et majuscules sont ignorés.
        </p>
      </div>

      <div className="mt-8 bg-white border border-slate-200 rounded-sm p-6">
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">
          <EnvelopeSimple size={14} /> Réimport depuis SendGrid (récupération de données)
        </div>
        <p className="text-xs text-slate-500 leading-relaxed mb-4">
          Reconstruit votre base prospects à partir des emails déjà envoyés via SendGrid. Pour chaque destinataire unique,
          un prospect canal email est créé avec l'étape 1 marquée comme envoyée (l'autopilot programmera l'étape 2 selon
          le scénario). Clé API SendGrid et email expéditeur doivent être configurés dans <strong>Paramètres</strong>.
        </p>

        <div className="flex items-center gap-3 mb-4">
          <label className="text-xs font-medium text-slate-600">Période à récupérer :</label>
          <select
            value={sinceDays}
            onChange={(e) => setSinceDays(parseInt(e.target.value))}
            className="text-sm border border-slate-300 rounded-sm px-2 py-1"
          >
            <option value={3}>3 derniers jours</option>
            <option value={7}>7 derniers jours (Free trial)</option>
            <option value={14}>14 derniers jours</option>
            <option value={30}>30 derniers jours</option>
          </select>
        </div>

        <div className="flex gap-2 flex-wrap">
          <Button
            data-testid="btn-sg-preview"
            onClick={async () => {
              setSgLoading(true); setSgResult(null);
              try {
                const res = await api.post("/import/sendgrid", { since_days: sinceDays, dry_run: true });
                setSgPreview(res.data);
                toast.success(`${res.data.unique_recipients} destinataires uniques détectés`);
              } catch (e) {
                toast.error(e.response?.data?.detail || "Aperçu impossible");
              } finally { setSgLoading(false); }
            }}
            disabled={sgLoading}
            variant="outline"
            className="rounded-sm"
          >
            <ArrowClockwise size={16} className="mr-2" />
            {sgLoading ? "Chargement…" : "Aperçu (dry-run)"}
          </Button>
          <Button
            data-testid="btn-sg-import"
            onClick={async () => {
              if (!sgPreview) { toast.error("Lance d'abord l'aperçu"); return; }
              if (!window.confirm(`Créer ${sgPreview.unique_recipients} prospects depuis SendGrid ?`)) return;
              setSgLoading(true); setSgResult(null);
              try {
                const res = await api.post("/import/sendgrid", { since_days: sinceDays, dry_run: false, mark_step1_sent: true });
                setSgResult(res.data);
                toast.success(`${res.data.created} prospects créés (${res.data.skipped_existing} déjà présents)`);
              } catch (e) {
                toast.error(e.response?.data?.detail || "Import impossible");
              } finally { setSgLoading(false); }
            }}
            disabled={sgLoading || !sgPreview}
            className="bg-[#002FA7] hover:bg-[#00227A] text-white rounded-sm"
          >
            <EnvelopeSimple size={16} className="mr-2" />
            Lancer l'import
          </Button>
        </div>

        {sgPreview && !sgResult && (
          <div className="mt-4 border border-slate-200 rounded-sm p-4">
            <div className="text-xs text-slate-500 mb-3">
              <strong>{sgPreview.messages_fetched}</strong> messages SendGrid récupérés ·{" "}
              <strong>{sgPreview.unique_recipients}</strong> destinataires uniques.
              Aperçu des 10 premiers :
            </div>
            <div className="max-h-72 overflow-y-auto">
              <table className="text-xs w-full">
                <thead className="text-slate-500 border-b border-slate-200">
                  <tr><th className="text-left py-1">Email</th><th className="text-left py-1">Entreprise</th><th className="text-left py-1">Sujet</th><th className="text-right py-1">Opens</th></tr>
                </thead>
                <tbody>
                  {(sgPreview.preview || []).map((p) => (
                    <tr key={p.email} className="border-b border-slate-100">
                      <td className="py-1 font-mono">{p.email}</td>
                      <td className="py-1">{p.entreprise}</td>
                      <td className="py-1 truncate max-w-[260px]" title={p.subject}>{p.subject}</td>
                      <td className="py-1 text-right tabular-nums">{p.opens}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {sgResult && (
          <div className="mt-4 border border-emerald-200 bg-emerald-50 rounded-sm p-4">
            <div className="flex items-center gap-2 text-emerald-700 font-semibold mb-3">
              <CheckCircle size={18} weight="fill" /> Import terminé
            </div>
            <div className="grid grid-cols-4 gap-3 text-center">
              {[["Créés", sgResult.created, "text-emerald-600"], ["Doublons", sgResult.skipped_existing, "text-amber-600"], ["Erreurs", sgResult.errors, "text-red-500"], ["Récupérés", sgResult.messages_fetched, "text-slate-600"]].map(([l, v, c]) => (
                <div key={l} className="border border-emerald-200 bg-white py-2 rounded-sm">
                  <div className={`font-heading text-xl font-bold tabular-nums ${c}`}>{v}</div>
                  <div className="text-[10px] uppercase text-slate-400">{l}</div>
                </div>
              ))}
            </div>
            <div className="text-xs text-emerald-700 mt-3">
              ✅ Sauvegarde automatique effectuée. <strong>Cliquez "Save to GitHub"</strong> pour rendre la récupération définitive.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
