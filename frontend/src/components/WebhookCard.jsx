import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy, EnvelopeOpen, Plugs } from "@phosphor-icons/react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const ACTION_STYLES = {
  repondu: "bg-emerald-100 text-emerald-800",
  interesse: "bg-amber-100 text-amber-800",
  desabonne: "bg-red-100 text-red-700",
};

export default function WebhookCard() {
  const [settings, setSettings] = useState(null);
  const [reponses, setReponses] = useState([]);

  useEffect(() => {
    api.get("/settings").then((res) => setSettings(res.data));
    api.get("/webhook/reponses?limit=20").then((res) => setReponses(res.data.items));
  }, []);

  if (!settings) return null;

  const base = `${process.env.REACT_APP_BACKEND_URL}/api/webhook`;
  const inboundUrl = `${base}/sendgrid/inbound?token=${settings.webhook_token}`;
  const eventsUrl = `${base}/sendgrid/events?token=${settings.webhook_token}`;

  const copy = (txt, label) => {
    navigator.clipboard.writeText(txt);
    toast.success(`${label} copiée`);
  };

  const saveReplyTo = async () => {
    await api.put("/settings", { email_reponse: settings.email_reponse });
    toast.success("Adresse de réponse enregistrée");
  };

  return (
    <div data-testid="webhook-card" className="mt-6 bg-white border border-slate-200 rounded-sm p-6">
      <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] font-semibold text-slate-500">
        <Plugs size={14} /> Webhook SendGrid — réponses automatiques
      </div>
      <p className="text-xs text-slate-500 mt-2 leading-relaxed">
        Détecte automatiquement les réponses et les « STOP » : le prospect passe en
        <strong> répondu</strong> ou <strong>opt-out</strong> et les relances s'arrêtent seules.
        Chaque réponse vous est aussi transférée par email.
      </p>

      <div className="mt-4 space-y-3">
        <div>
          <label className="text-[11px] font-medium text-slate-600 mb-1 block">
            1. Réponses (Inbound Parse) — SendGrid → Settings → Inbound Parse
          </label>
          <div className="flex gap-2">
            <Input data-testid="input-inbound-url" readOnly value={inboundUrl} className="rounded-sm h-9 text-xs font-mono" />
            <Button data-testid="btn-copy-inbound" variant="outline" className="rounded-sm h-9 px-3 shrink-0"
              onClick={() => copy(inboundUrl, "URL Inbound Parse")}>
              <Copy size={15} />
            </Button>
          </div>
        </div>
        <div>
          <label className="text-[11px] font-medium text-slate-600 mb-1 block">
            2. Événements (bounces, désabos) — SendGrid → Settings → Mail Settings → Event Webhook
          </label>
          <div className="flex gap-2">
            <Input data-testid="input-events-url" readOnly value={eventsUrl} className="rounded-sm h-9 text-xs font-mono" />
            <Button data-testid="btn-copy-events" variant="outline" className="rounded-sm h-9 px-3 shrink-0"
              onClick={() => copy(eventsUrl, "URL Event Webhook")}>
              <Copy size={15} />
            </Button>
          </div>
        </div>
        <div>
          <label className="text-[11px] font-medium text-slate-600 mb-1 block">
            3. Adresse de réponse (Reply-To, ex : simon@reponse.sitequivend.fr)
          </label>
          <div className="flex gap-2">
            <Input data-testid="input-email-reponse" value={settings.email_reponse || ""}
              onChange={(e) => setSettings({ ...settings, email_reponse: e.target.value })}
              placeholder="simon@reponse.sitequivend.fr" className="rounded-sm h-9" />
            <Button data-testid="btn-save-email-reponse" variant="outline" className="rounded-sm h-9 shrink-0" onClick={saveReplyTo}>
              Enregistrer
            </Button>
          </div>
          <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
            Configuration DNS : créez un enregistrement <strong>MX</strong> sur le sous-domaine
            <code className="bg-slate-100 px-1 mx-1">reponse.sitequivend.fr</code> pointant vers
            <code className="bg-slate-100 px-1 mx-1">mx.sendgrid.net</code> (priorité 10), puis déclarez ce
            sous-domaine comme hostname dans Inbound Parse avec l'URL n°1. Les réponses des prospects
            arriveront ici ET vous seront transférées sur {settings.email_expediteur || "votre boîte"}.
          </p>
        </div>
      </div>

      <div className="mt-5 border-t border-slate-100 pt-4">
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-3">
          <EnvelopeOpen size={14} /> Réponses reçues
        </div>
        {reponses.length === 0 ? (
          <p data-testid="reponses-vide" className="text-xs text-slate-400">
            Aucune réponse reçue pour le moment. Elles apparaîtront ici dès que le webhook sera configuré chez SendGrid.
          </p>
        ) : (
          <div data-testid="reponses-list" className="space-y-1.5 max-h-64 overflow-y-auto">
            {reponses.map((r) => (
              <div key={r.id} className="text-xs py-2 px-2.5 bg-slate-50 rounded-sm">
                <div className="flex items-center gap-2">
                  <span className={`shrink-0 px-1.5 py-0.5 rounded-sm font-semibold ${ACTION_STYLES[r.action] || "bg-slate-200"}`}>
                    {r.action}
                  </span>
                  <span className="font-medium text-slate-700 truncate">{r.entreprise || r.de}</span>
                  <span className="text-slate-400 ml-auto shrink-0">
                    {new Date(r.date).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
                <div className="text-slate-500 truncate mt-1">« {r.objet} » — {r.texte?.slice(0, 120)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
