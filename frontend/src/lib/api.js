import axios from "axios";

const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`,
});

export default api;

export const NIVEAU_STYLES = {
  "Très chaud": "bg-amber-100 text-amber-800 border-amber-200",
  Chaud: "bg-orange-100 text-orange-800 border-orange-200",
  Tiède: "bg-blue-50 text-blue-700 border-blue-200",
  Froid: "bg-slate-100 text-slate-600 border-slate-200",
};

export const STATUT_LABELS = {
  a_contacter: "À contacter",
  repondu: "Répondu",
  rdv: "RDV pris",
  gagne: "Gagné ✅",
  perdu: "Perdu",
  opt_out: "Opt-out",
  epuise: "Séquence épuisée",
};

export const STATUT_STYLES = {
  a_contacter: "bg-blue-50 text-blue-700 border-blue-200",
  repondu: "bg-emerald-100 text-emerald-800 border-emerald-200",
  rdv: "bg-violet-100 text-violet-800 border-violet-200",
  gagne: "bg-emerald-100 text-emerald-800 border-emerald-200",
  perdu: "bg-slate-100 text-slate-500 border-slate-200",
  opt_out: "bg-red-50 text-red-700 border-red-200",
  epuise: "bg-slate-100 text-slate-500 border-slate-200",
};

export const PROFIL_LABELS = {
  pas_de_site: "Pas de site",
  site_ancien: "Site ancien",
  signal_chaud: "Signal chaud",
  site_moyen: "Site moyen",
};
