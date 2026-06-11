import { useRef, useState } from "react";
import { toast } from "sonner";
import { UploadSimple, FileXls, CheckCircle } from "@phosphor-icons/react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function ImportPage() {
  const inputRef = useRef(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

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
          <div className="grid grid-cols-3 gap-4 text-center mb-4">
            {[["Importés", result.importes, "text-emerald-600"], ["Doublons ignorés", result.doublons, "text-amber-600"], ["Erreurs", result.erreurs, "text-red-500"]].map(([l, v, c]) => (
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
    </div>
  );
}
