import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plug, CheckCircle, XCircle, Eye, EyeSlash } from "@phosphor-icons/react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";

const PRESETS = {
  ovh: { host: "ssl0.ovh.net", port: 993, label: "OVH" },
  gmail: { host: "imap.gmail.com", port: 993, label: "Gmail (mot de passe d'application requis)" },
  outlook: { host: "outlook.office365.com", port: 993, label: "Outlook / Office 365" },
  ionos: { host: "imap.ionos.fr", port: 993, label: "IONOS / 1&1" },
  custom: { host: "", port: 993, label: "Autre fournisseur" },
};

export default function ImapCard() {
  const [s, setS] = useState({
    imap_host: "", imap_port: 993, imap_user: "", imap_password: "",
    imap_password_set: false, imap_folder: "INBOX",
  });
  const [showPwd, setShowPwd] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [preset, setPreset] = useState("ovh");

  const load = async () => {
    try {
      const res = await api.get("/settings");
      setS({
        imap_host: res.data.imap_host || "",
        imap_port: res.data.imap_port || 993,
        imap_user: res.data.imap_user || res.data.email_expediteur || "",
        imap_password: "",
        imap_password_set: !!res.data.imap_password_set,
        imap_folder: res.data.imap_folder || "INBOX",
      });
      // Détecte le préset
      const cur = res.data.imap_host || "";
      const match = Object.entries(PRESETS).find(([_k, v]) => v.host === cur);
      setPreset(match ? match[0] : (cur ? "custom" : "ovh"));
    } catch (e) { console.error(e); }
  };
  useEffect(() => { load(); }, []);

  const applyPreset = (key) => {
    setPreset(key);
    const p = PRESETS[key];
    if (p.host) {
      setS((prev) => ({ ...prev, imap_host: p.host, imap_port: p.port }));
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        imap_host: s.imap_host,
        imap_port: parseInt(s.imap_port) || 993,
        imap_user: s.imap_user,
        imap_folder: s.imap_folder,
      };
      if (s.imap_password) payload.imap_password = s.imap_password;
      await api.put("/settings", payload);
      toast.success("Paramètres IMAP enregistrés");
      setS((prev) => ({ ...prev, imap_password: "", imap_password_set: prev.imap_password_set || !!prev.imap_password }));
      await load();
    } catch (e) {
      toast.error("Sauvegarde impossible");
    } finally { setSaving(false); }
  };

  const test = async () => {
    setTesting(true);
    try {
      // Si l'utilisateur vient de taper un mot de passe, on doit d'abord le sauver
      if (s.imap_password) await save();
      const res = await api.post("/inbox/test");
      if (res.data.ok) {
        toast.success(`Connexion OK — ${res.data.folders_sample?.length || 0} dossiers détectés`);
      } else {
        toast.error(`Connexion KO : ${res.data.error}`);
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Test impossible");
    } finally { setTesting(false); }
  };

  return (
    <div className="mt-6 bg-white border border-slate-200 rounded-sm p-6">
      <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] font-semibold text-slate-500 mb-3">
        <Plug size={14} /> Boîte mail IMAP (lecture des réponses)
      </div>
      <p className="text-xs text-slate-500 leading-relaxed mb-4">
        Connecte ta boîte email pour que l'app récupère automatiquement les réponses des prospects.
        L'app n'envoie jamais de mail depuis IMAP — elle ne fait que lire la boîte pour identifier les réponses.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs uppercase tracking-wider font-semibold text-slate-500 mb-1">Fournisseur</label>
          <select
            value={preset}
            onChange={(e) => applyPreset(e.target.value)}
            className="w-full text-sm border border-slate-300 rounded-sm px-3 py-2"
          >
            {Object.entries(PRESETS).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs uppercase tracking-wider font-semibold text-slate-500 mb-1">Dossier</label>
          <input
            value={s.imap_folder}
            onChange={(e) => setS({...s, imap_folder: e.target.value})}
            placeholder="INBOX"
            className="w-full text-sm border border-slate-300 rounded-sm px-3 py-2 font-mono"
          />
        </div>

        <div>
          <label className="block text-xs uppercase tracking-wider font-semibold text-slate-500 mb-1">Serveur IMAP</label>
          <input
            data-testid="imap-host"
            value={s.imap_host}
            onChange={(e) => setS({...s, imap_host: e.target.value})}
            placeholder="ssl0.ovh.net"
            className="w-full text-sm border border-slate-300 rounded-sm px-3 py-2 font-mono"
          />
        </div>
        <div>
          <label className="block text-xs uppercase tracking-wider font-semibold text-slate-500 mb-1">Port (SSL)</label>
          <input
            value={s.imap_port}
            onChange={(e) => setS({...s, imap_port: e.target.value})}
            type="number"
            className="w-full text-sm border border-slate-300 rounded-sm px-3 py-2 font-mono"
          />
        </div>

        <div>
          <label className="block text-xs uppercase tracking-wider font-semibold text-slate-500 mb-1">Identifiant (email)</label>
          <input
            data-testid="imap-user"
            value={s.imap_user}
            onChange={(e) => setS({...s, imap_user: e.target.value})}
            placeholder="simon@sitequivend.fr"
            className="w-full text-sm border border-slate-300 rounded-sm px-3 py-2 font-mono"
          />
        </div>
        <div>
          <label className="block text-xs uppercase tracking-wider font-semibold text-slate-500 mb-1">
            Mot de passe {s.imap_password_set && <span className="text-emerald-600 lowercase normal-case">• déjà enregistré</span>}
          </label>
          <div className="relative">
            <input
              data-testid="imap-password"
              value={s.imap_password}
              onChange={(e) => setS({...s, imap_password: e.target.value})}
              type={showPwd ? "text" : "password"}
              placeholder={s.imap_password_set ? "•••••••• (laisser vide pour ne pas changer)" : "Mot de passe email"}
              className="w-full text-sm border border-slate-300 rounded-sm px-3 py-2 font-mono pr-10"
            />
            <button
              type="button"
              onClick={() => setShowPwd(!showPwd)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
            >
              {showPwd ? <EyeSlash size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>
      </div>

      <div className="flex gap-2 mt-5">
        <Button
          data-testid="btn-imap-save"
          onClick={save}
          disabled={saving}
          className="bg-[#002FA7] hover:bg-[#00227A] text-white rounded-sm"
        >
          {saving ? "Sauvegarde..." : "Enregistrer"}
        </Button>
        <Button
          data-testid="btn-imap-test"
          onClick={test}
          disabled={testing || !s.imap_host || !s.imap_user || (!s.imap_password && !s.imap_password_set)}
          variant="outline"
          className="rounded-sm"
        >
          {testing ? "Test..." : "Tester la connexion"}
        </Button>
      </div>

      <div className="mt-4 text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded-sm p-3">
        <strong>Aide rapide :</strong>
        <ul className="list-disc pl-5 mt-1 space-y-0.5">
          <li><strong>OVH</strong> : serveur <code className="font-mono">ssl0.ovh.net</code>, port <code className="font-mono">993</code>, mot de passe = celui de ta boîte email.</li>
          <li><strong>Gmail</strong> : active la validation en 2 étapes puis crée un "mot de passe d'application" sur <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer" className="underline">myaccount.google.com/apppasswords</a>.</li>
          <li><strong>Le mot de passe est stocké chiffré dans la base</strong> (jamais loggué ni renvoyé au navigateur).</li>
        </ul>
      </div>
    </div>
  );
}
