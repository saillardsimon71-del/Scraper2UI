import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FloppyDisk, WhatsappLogo, LinkedinLogo } from "@phosphor-icons/react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const VARIABLES = ["{entreprise}", "{ville}", "{metier}", "{site_web}", "{signal}", "{note_site}", "{prenom_exp}", "{lien_rdv}"];

export default function Scenarios() {
  const [scenarios, setScenarios] = useState([]);

  const load = async () => {
    const res = await api.get("/scenarios");
    setScenarios(res.data.scenarios);
  };

  useEffect(() => {
    load();
  }, []);

  const updateEtape = (profil, idx, field, value) => {
    setScenarios((prev) =>
      prev.map((sc) =>
        sc.profil === profil
          ? { ...sc, etapes: sc.etapes.map((e, i) => (i === idx ? { ...e, [field]: value } : e)) }
          : sc
      )
    );
  };

  const save = async (sc) => {
    await api.put(`/scenarios/${sc.profil}`, {
      etapes: sc.etapes.map((e) => ({ ...e, delai_jours: Number(e.delai_jours) || 0 })),
    });
    toast.success(`Séquence « ${sc.label} » enregistrée`);
  };

  if (!scenarios.length) return <div className="p-8 text-sm text-slate-400">Chargement…</div>;

  return (
    <div className="p-8 fade-up max-w-4xl">
      <h1 className="text-4xl tracking-tighter font-bold text-[#111111]">Séquences & Templates</h1>
      <p className="text-sm text-slate-500 mt-1 mb-6">
        Chaque profil de prospect a sa propre séquence de relance. Les variables sont remplacées automatiquement à l'envoi.
      </p>

      <div className="flex flex-wrap gap-1.5 mb-6">
        {VARIABLES.map((v) => (
          <button
            key={v}
            onClick={() => {
              navigator.clipboard.writeText(v);
              toast.success(`${v} copié`);
            }}
            className="font-mono text-[11px] bg-white border border-slate-200 hover:border-[#002FA7] px-2 py-1 rounded-sm transition-colors"
          >
            {v}
          </button>
        ))}
      </div>

      <Tabs defaultValue={scenarios[0].profil}>
        <TabsList className="rounded-sm bg-white border border-slate-200 h-auto p-1">
          {scenarios.map((sc) => (
            <TabsTrigger
              key={sc.profil}
              value={sc.profil}
              data-testid={`tab-scenario-${sc.profil}`}
              className="rounded-sm data-[state=active]:bg-[#111111] data-[state=active]:text-white px-4 py-2"
            >
              {sc.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {scenarios.map((sc) => (
          <TabsContent key={sc.profil} value={sc.profil} className="mt-4 space-y-4">
            <p className="text-xs text-slate-500">{sc.description}</p>
            {sc.etapes.map((e, idx) => (
              <div key={e.etape} className="bg-white border border-slate-200 rounded-sm p-5">
                <div className="flex items-center gap-3 mb-3">
                  <span className="font-heading font-bold text-lg">Étape {e.etape}</span>
                  <Select value={e.canal} onValueChange={(v) => updateEtape(sc.profil, idx, "canal", v)}>
                    <SelectTrigger data-testid={`select-canal-${sc.profil}-${e.etape}`} className="w-40 h-8 rounded-sm text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="whatsapp">
                        <span className="flex items-center gap-1.5"><WhatsappLogo size={13} className="text-[#25D366]" /> WhatsApp</span>
                      </SelectItem>
                      <SelectItem value="linkedin">
                        <span className="flex items-center gap-1.5"><LinkedinLogo size={13} className="text-[#0A66C2]" /> LinkedIn</span>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  <div className="flex items-center gap-1.5 text-xs text-slate-500">
                    {idx === 0 ? "Immédiat" : (
                      <>
                        J+
                        <Input
                          data-testid={`input-delai-${sc.profil}-${e.etape}`}
                          type="number"
                          min={1}
                          value={e.delai_jours}
                          onChange={(ev) => updateEtape(sc.profil, idx, "delai_jours", ev.target.value)}
                          className="w-16 h-8 rounded-sm text-xs"
                        />
                        après l'étape précédente
                      </>
                    )}
                  </div>
                </div>
                <Textarea
                  data-testid={`textarea-template-${sc.profil}-${e.etape}`}
                  value={e.template}
                  onChange={(ev) => updateEtape(sc.profil, idx, "template", ev.target.value)}
                  rows={3}
                  className="rounded-sm text-sm"
                />
              </div>
            ))}
            <Button
              data-testid={`btn-save-scenario-${sc.profil}`}
              onClick={() => save(sc)}
              className="bg-[#002FA7] hover:bg-[#00227A] text-white rounded-sm"
            >
              <FloppyDisk size={16} className="mr-2" /> Enregistrer la séquence
            </Button>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
