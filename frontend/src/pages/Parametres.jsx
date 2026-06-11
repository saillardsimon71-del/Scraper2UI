import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FloppyDisk, Sparkle } from "@phosphor-icons/react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import AutopilotCard from "@/components/AutopilotCard";
import WebhookCard from "@/components/WebhookCard";
import BackupCard from "@/components/BackupCard";

export default function Parametres() {
  const [form, setForm] = useState({
    prenom_expediteur: "", lien_rdv: "", serper_api_key: "", sendgrid_api_key: "", email_expediteur: "",
  });

  useEffect(() => {
    api.get("/settings").then((res) => setForm(res.data));
  }, []);

  const save = async () => {
    await api.put("/settings", form);
    toast.success("Paramètres enregistrés");
  };

  return (
    <div className="p-8 fade-up max-w-2xl">
      <h1 className="text-4xl tracking-tighter font-bold text-[#111111]">Paramètres</h1>
      <p className="text-sm text-slate-500 mt-1 mb-8">Identité d'expéditeur, lien de RDV et clés API.</p>

      <div className="bg-white border border-slate-200 rounded-sm p-6 space-y-5">
        <div>
          <label className="text-xs font-medium text-slate-600 mb-1 block">Votre prénom (variable {"{prenom_exp}"})</label>
          <Input
            data-testid="input-prenom-exp"
            value={form.prenom_expediteur}
            onChange={(e) => setForm({ ...form, prenom_expediteur: e.target.value })}
            placeholder="Simon"
            className="rounded-sm"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600 mb-1 block">Lien de RDV (variable {"{lien_rdv}"})</label>
          <Input
            data-testid="input-lien-rdv"
            value={form.lien_rdv}
            onChange={(e) => setForm({ ...form, lien_rdv: e.target.value })}
            placeholder="https://calendly.com/votre-lien"
            className="rounded-sm"
          />
          <p className="text-[11px] text-slate-400 mt-1">Inséré dans les messages où la variable est présente.</p>
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600 mb-1 block">Clé Serper (recherche Google des sites — optionnel)</label>
          <Input
            data-testid="input-serper-key"
            type="password"
            value={form.serper_api_key}
            onChange={(e) => setForm({ ...form, serper_api_key: e.target.value })}
            placeholder="Clé API serper.dev"
            className="rounded-sm"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Si renseignée, le scraper cherche le site web des entreprises sans site connu via Google.
          </p>
        </div>
        <div className="border-t border-slate-100 pt-4">
          <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-3">Canal email (SendGrid)</div>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Clé API SendGrid</label>
              <Input
                data-testid="input-sendgrid-key"
                type="password"
                value={form.sendgrid_api_key}
                onChange={(e) => setForm({ ...form, sendgrid_api_key: e.target.value })}
                placeholder="SG.xxxxx"
                className="rounded-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Email expéditeur vérifié</label>
              <Input
                data-testid="input-email-expediteur"
                value={form.email_expediteur}
                onChange={(e) => setForm({ ...form, email_expediteur: e.target.value })}
                placeholder="simon@votredomaine.fr"
                className="rounded-sm"
              />
              <p className="text-[11px] text-slate-400 mt-1">
                Doit être un sender vérifié dans SendGrid. Sans clé, le bouton email ouvre votre client mail (mailto).
              </p>
            </div>
          </div>
        </div>
        <Button data-testid="btn-save-settings" onClick={save} className="bg-[#002FA7] hover:bg-[#00227A] text-white rounded-sm">
          <FloppyDisk size={16} className="mr-2" /> Enregistrer
        </Button>
      </div>

      <AutopilotCard />

      <WebhookCard />

      <BackupCard />

      <div className="mt-6 bg-white border border-slate-200 rounded-sm p-6">
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">
          <Sparkle size={14} /> IA — amélioration des messages
        </div>
        <p className="text-xs text-slate-500 leading-relaxed">
          L'amélioration IA des messages utilise la clé universelle Emergent (GPT-5), déjà configurée. Aucune action requise.
        </p>
      </div>
    </div>
  );
}
