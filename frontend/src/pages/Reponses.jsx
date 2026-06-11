import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  EnvelopeOpen, ArrowsClockwise, MagicWand, User, Clock,
  CheckCircle, XCircle, Warning, Plug,
} from "@phosphor-icons/react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";

const ACTION_LABEL = {
  repondu: { label: "Réponse", color: "bg-blue-100 text-blue-700 border-blue-200" },
  interesse: { label: "Intéressé", color: "bg-emerald-100 text-emerald-700 border-emerald-200" },
  desabonne: { label: "Désabonné", color: "bg-red-100 text-red-700 border-red-200" },
};

function fmt(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("fr-FR", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

export default function Reponses() {
  const [replies, setReplies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [sinceDays, setSinceDays] = useState(30);
  const [lastSync, setLastSync] = useState(null);
  const [settings, setSettings] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [r, s] = await Promise.all([
        api.get("/replies?limit=200"),
        api.get("/settings"),
      ]);
      setReplies(r.data.items || []);
      setSettings(s.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const sync = async () => {
    setSyncing(true);
    try {
      const res = await api.post("/inbox/sync", { since_days: sinceDays, dry_run: false });
      setLastSync(res.data);
      toast.success(
        `${res.data.linked} liées · ${res.data.orphans} orphelines · ${res.data.already_imported} déjà connues`
      );
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Synchronisation impossible");
    } finally {
      setSyncing(false);
    }
  };

  const imapReady = settings?.imap_host && settings?.imap_user && settings?.imap_password_set;

  return (
    <div className="px-10 py-8">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-slate-400 mb-1">Inbox</p>
        <h1 className="font-heading font-bold text-4xl mb-2 leading-tight">Réponses prospects</h1>
        <p className="text-sm text-slate-500">
          Toutes les réponses reçues depuis votre boîte mail (IMAP) ou via SendGrid Inbound Parse.
          Liées automatiquement aux prospects et classées par intention (intéressé, désabonnement, simple réponse).
        </p>
      </div>

      {/* Bandeau d'état IMAP */}
      <div className={`mb-6 p-4 rounded-sm border ${imapReady ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
        <div className="flex items-start gap-3">
          <Plug size={20} weight="fill" className={imapReady ? "text-emerald-600" : "text-amber-600"} />
          <div className="flex-1">
            {imapReady ? (
              <>
                <div className="text-sm font-semibold text-emerald-800">Boîte mail connectée</div>
                <div className="text-xs text-emerald-700">
                  {settings.imap_user} · {settings.imap_host}:{settings.imap_port}
                </div>
              </>
            ) : (
              <>
                <div className="text-sm font-semibold text-amber-800">Boîte mail non configurée</div>
                <div className="text-xs text-amber-700">
                  Configurez vos identifiants IMAP dans <Link to="/parametres" className="underline font-semibold">Paramètres</Link> pour récupérer automatiquement vos réponses.
                </div>
              </>
            )}
          </div>
          {imapReady && (
            <div className="flex items-center gap-3">
              <select
                value={sinceDays}
                onChange={(e) => setSinceDays(parseInt(e.target.value))}
                className="text-sm border border-emerald-300 rounded-sm px-2 py-1 bg-white"
              >
                <option value={7}>7 derniers jours</option>
                <option value={14}>14 derniers jours</option>
                <option value={30}>30 derniers jours</option>
                <option value={60}>60 derniers jours</option>
                <option value={90}>90 derniers jours</option>
              </select>
              <Button
                data-testid="btn-inbox-sync"
                onClick={sync}
                disabled={syncing}
                className="bg-[#002FA7] hover:bg-[#00227A] text-white rounded-sm"
              >
                <ArrowsClockwise size={16} className={`mr-2 ${syncing ? "animate-spin" : ""}`} />
                {syncing ? "Synchronisation..." : "Synchroniser ma boîte"}
              </Button>
            </div>
          )}
        </div>
        {lastSync && (
          <div className="mt-3 grid grid-cols-4 gap-2 text-center text-xs">
            <div className="bg-white border border-emerald-200 rounded-sm py-2">
              <div className="font-heading text-xl font-bold tabular-nums text-slate-700">{lastSync.messages_read}</div>
              <div className="text-[10px] uppercase text-slate-400">Mails lus</div>
            </div>
            <div className="bg-white border border-emerald-200 rounded-sm py-2">
              <div className="font-heading text-xl font-bold tabular-nums text-emerald-600">{lastSync.linked}</div>
              <div className="text-[10px] uppercase text-slate-400">Liées</div>
            </div>
            <div className="bg-white border border-emerald-200 rounded-sm py-2">
              <div className="font-heading text-xl font-bold tabular-nums text-amber-600">{lastSync.orphans}</div>
              <div className="text-[10px] uppercase text-slate-400">Orphelines</div>
            </div>
            <div className="bg-white border border-emerald-200 rounded-sm py-2">
              <div className="font-heading text-xl font-bold tabular-nums text-slate-500">{lastSync.already_imported}</div>
              <div className="text-[10px] uppercase text-slate-400">Déjà connues</div>
            </div>
          </div>
        )}
      </div>

      {/* Liste des réponses */}
      <div className="bg-white border border-slate-200 rounded-sm">
        <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
          <div className="text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 flex items-center gap-2">
            <EnvelopeOpen size={14} /> {replies.length} réponse{replies.length > 1 ? "s" : ""}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={load}
            disabled={loading}
            className="rounded-sm text-xs"
          >
            <ArrowsClockwise size={14} className={`mr-1 ${loading ? "animate-spin" : ""}`} />
            Actualiser
          </Button>
        </div>
        {replies.length === 0 ? (
          <div className="py-16 text-center">
            <EnvelopeOpen size={40} className="mx-auto text-slate-300 mb-3" />
            <p className="text-sm text-slate-500">
              Aucune réponse pour le moment.
              {imapReady && " Cliquez sur \"Synchroniser ma boîte\" pour les récupérer."}
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {replies.map((r) => {
              const action = ACTION_LABEL[r.action] || ACTION_LABEL.repondu;
              return (
                <div key={r.id} className="p-5 hover:bg-slate-50 transition-colors">
                  <div className="flex items-start justify-between gap-4 mb-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <User size={14} className="text-slate-400 shrink-0" />
                        <span className="font-semibold text-sm truncate">{r.de_complet || r.de}</span>
                        <span className="text-xs text-slate-400 font-mono">&lt;{r.de}&gt;</span>
                      </div>
                      <div className="text-sm text-slate-700 font-medium truncate">{r.objet || "(sans objet)"}</div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`text-[10px] uppercase tracking-wider px-2 py-1 rounded-sm border font-semibold ${action.color}`}>
                        {action.label}
                      </span>
                      <span className="text-xs text-slate-400 inline-flex items-center gap-1">
                        <Clock size={12} /> {fmt(r.date)}
                      </span>
                    </div>
                  </div>
                  <div className="text-xs text-slate-600 leading-relaxed bg-slate-50 border border-slate-200 rounded-sm p-3 whitespace-pre-line max-h-32 overflow-y-auto">
                    {r.extrait || r.texte || "(contenu vide)"}
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-xs">
                    {r.prospect_id ? (
                      <Link
                        to={`/prospects?id=${r.prospect_id}`}
                        className="text-[#002FA7] hover:underline font-medium inline-flex items-center gap-1"
                      >
                        <CheckCircle size={12} weight="fill" />
                        Fiche prospect {r.entreprise && `· ${r.entreprise}`}
                      </Link>
                    ) : (
                      <span className="text-amber-700 inline-flex items-center gap-1">
                        <Warning size={12} weight="fill" />
                        Aucun prospect lié (orpheline)
                      </span>
                    )}
                    {r.source && (
                      <span className="text-slate-400 ml-auto">via {r.source}</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
