import { Wrench } from "lucide-react";
import { featureDisabledMessage } from "../../../lib/featureFlags";
import { deviceLanguage } from "../../../lib/locale";

export default function FeatureUnavailable({ flags, flagKey }) {
  const language = deviceLanguage();
  return <section className="dincr-feature-unavailable" role="status"><Wrench size={30}/><h2>{language === "es" ? "En mantenimiento" : "Under maintenance"}</h2><p>{featureDisabledMessage(flags, flagKey, language)}</p><span>{language === "es" ? "No perdiste información. Volverá a aparecer cuando sea seguro usarla." : "No data was lost. It will return when it is safe to use."}</span></section>;
}
