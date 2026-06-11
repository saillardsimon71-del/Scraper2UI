import { Lightning, ChatCircleText, ShieldCheck, Quotes } from "@phosphor-icons/react";

const REGLES_OR = [
  {
    titre: "Répondez dans l'heure",
    texte: "Un artisan qui répond est chaud maintenant, plus dans 3 jours. La vitesse de réponse fait plus que la qualité du pitch.",
  },
  {
    titre: "Ne pitchez jamais, posez des questions",
    texte: "À chaque objection, répondez par une question. Celui qui pose les questions mène la conversation.",
  },
  {
    titre: "Parlez chantiers, pas pixels",
    texte: "Jamais de jargon (SEO, responsive, CMS). Parlez demandes de devis, appels entrants, clients qui comparent.",
  },
];

const TRAME = [
  {
    etape: 1,
    titre: "Répondre vite, court, humain",
    texte: "Pas de pavé. Remerciez et enchaînez direct sur une question simple.",
    exemple: "Merci pour votre retour ! Avant de vous montrer quoi que ce soit, une question : aujourd'hui, vos clients vous trouvent comment ? Bouche-à-oreille ?",
  },
  {
    etape: 2,
    titre: "Qualifier la douleur",
    texte: "Faites-le parler de son activité. Vous cherchez : combien de demandes par mois, y a-t-il une saison creuse, a-t-il déjà perdu un chantier face à un concurrent plus visible.",
    exemple: "Et ça vous fait combien de demandes par mois en ce moment ? Vous avez des périodes plus creuses ?",
  },
  {
    etape: 3,
    titre: "Reformuler sa douleur avec ses mots",
    texte: "Avant de parler solution, montrez que vous avez compris. C'est ce qui crée la confiance.",
    exemple: "Donc si je résume : le bouche-à-oreille marche, mais c'est irrégulier, et l'hiver c'est plus calme. C'est ça ?",
  },
  {
    etape: 4,
    titre: "Proposer un créneau précis (jamais « quand êtes-vous dispo ? »)",
    texte: "Donnez deux choix fermés. Un artisan répond mieux à un choix qu'à une question ouverte.",
    exemple: "Je vous montre en 10 minutes à quoi ressemblerait votre site. Demain 12h30 ou plutôt 18h ?",
  },
  {
    etape: 5,
    titre: "Confirmer par écrit + rappel le matin même",
    texte: "Envoyez la confirmation tout de suite, puis un rappel court le matin du RDV. Les artisans oublient — ce n'est pas du désintérêt, c'est le chantier.",
    exemple: "C'est noté pour demain 18h, je vous appelle sur ce numéro. Bonne fin de journée !",
  },
];

const OBJECTIONS = [
  {
    objection: "J'ai pas le temps de m'en occuper",
    reponse: "C'est justement pour ça que je livre en 72 h. Vous m'envoyez 5 photos de chantiers et votre numéro — je m'occupe de tout, vous validez, c'est en ligne. Ça vous prend 10 minutes en tout.",
    pourquoi: "L'objection n'est pas le temps, c'est la peur d'un projet interminable. Montrez que l'effort demandé est minuscule.",
  },
  {
    objection: "C'est trop cher",
    reponse: "Ça démarre à 300 €. Un seul chantier décroché grâce au site le rembourse. D'ailleurs, un chantier moyen, c'est combien chez vous ?",
    pourquoi: "Ramenez toujours le prix à la valeur d'un chantier. La question finale lui fait faire le calcul lui-même.",
  },
  {
    objection: "J'ai déjà un neveu / un copain qui fait ça",
    reponse: "Très bien ! Et il est en ligne, le site ? … Souvent ça traîne des mois. Moi c'est livré en 72 h, et tout vous appartient — si votre neveu veut reprendre la main ensuite, aucun souci.",
    pourquoi: "Ne critiquez jamais le neveu. La question « il est en ligne ? » suffit : dans 90 % des cas, non.",
  },
  {
    objection: "J'ai déjà assez de clients",
    reponse: "Parfait, c'est même le meilleur moment : un site sert aussi à choisir ses chantiers et monter ses prix, pas juste à en trouver plus. Et quand un gros client vous cherche sur Google avant de signer, il trouve quoi ?",
    pourquoi: "Déplacez l'enjeu : visibilité = crédibilité et meilleurs chantiers, pas seulement volume.",
  },
  {
    objection: "Le bouche-à-oreille me suffit",
    reponse: "Le bouche-à-oreille continue — sauf qu'aujourd'hui il passe par Google : on vous recommande, le client tape votre nom… et ne trouve rien. Un site, c'est juste votre bouche-à-oreille en ligne.",
    pourquoi: "Ne combattez pas le bouche-à-oreille, prolongez-le. C'est son argument, retournez-le en votre faveur.",
  },
  {
    objection: "Envoyez-moi une doc, on verra plus tard",
    reponse: "Je peux, mais soyons honnêtes : une doc finit à la poubelle. 10 minutes au téléphone et je vous montre directement à quoi ressemblerait VOTRE site, avec VOS chantiers. Demain 12h30 ou 18h ?",
    pourquoi: "« Envoyez une doc » = enterrement poli. Refusez avec humour et revenez au choix fermé de créneau.",
  },
];

export default function ScriptVente() {
  return (
    <div className="p-8 fade-up max-w-4xl">
      <h1 className="text-4xl tracking-tighter font-bold text-[#111111]">Script de vente</h1>
      <p className="text-sm text-slate-500 mt-1 mb-8">
        Un prospect a répondu ? C'est ici que le deal se gagne. Trame de conversation + réponses aux objections classiques des artisans.
      </p>

      {/* Règles d'or */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-10" data-testid="regles-or">
        {REGLES_OR.map((r, i) => (
          <div key={i} className="bg-[#111111] text-white rounded-sm p-5">
            <div className="flex items-center gap-2 mb-2">
              <Lightning size={16} weight="fill" className="text-[#25D366]" />
              <div className="font-heading font-semibold text-sm">{r.titre}</div>
            </div>
            <p className="text-xs text-white/60 leading-relaxed">{r.texte}</p>
          </div>
        ))}
      </div>

      {/* Trame de conversation */}
      <div className="flex items-center gap-2 mb-4">
        <ChatCircleText size={20} weight="bold" className="text-[#002FA7]" />
        <h2 className="text-lg font-heading font-bold text-[#111111]">La trame après une réponse</h2>
      </div>
      <div className="space-y-3 mb-10" data-testid="trame-conversation">
        {TRAME.map((t) => (
          <div key={t.etape} className="bg-white border border-slate-200 rounded-sm p-5 flex gap-4">
            <div className="shrink-0 w-9 h-9 rounded-sm bg-[#002FA7] text-white font-heading font-bold flex items-center justify-center">
              {t.etape}
            </div>
            <div className="min-w-0">
              <div className="font-semibold text-[#111111] text-sm">{t.titre}</div>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">{t.texte}</p>
              <div className="mt-2 bg-slate-50 border-l-2 border-[#25D366] px-3 py-2 text-xs text-slate-700 italic">
                “{t.exemple}”
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Objections */}
      <div className="flex items-center gap-2 mb-4">
        <ShieldCheck size={20} weight="bold" className="text-[#002FA7]" />
        <h2 className="text-lg font-heading font-bold text-[#111111]">Les 6 objections classiques — et quoi répondre</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="objections-grid">
        {OBJECTIONS.map((o, i) => (
          <div key={i} data-testid="objection-card" className="bg-white border border-slate-200 rounded-sm p-5 flex flex-col">
            <div className="flex items-start gap-2 mb-3">
              <Quotes size={16} weight="fill" className="text-amber-500 shrink-0 mt-0.5" />
              <div className="font-semibold text-[#111111] text-sm">« {o.objection} »</div>
            </div>
            <p className="text-sm text-slate-700 leading-relaxed flex-1">{o.reponse}</p>
            <div className="mt-3 pt-3 border-t border-slate-100 text-[11px] text-slate-400 leading-relaxed">
              <span className="uppercase tracking-[0.15em] font-semibold text-slate-500">Pourquoi ça marche · </span>
              {o.pourquoi}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
