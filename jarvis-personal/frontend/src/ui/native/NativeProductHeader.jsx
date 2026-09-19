import { MoreHorizontal } from "lucide-react";
import { deviceLanguage, tx } from "../../lib/locale";

export default function NativeProductHeader({ product, subtitle, avatar, onProfile, trailing }) {
  const language = deviceLanguage();
  return (
    <header className="native-product-header">
      <div className="native-product-title">
        <strong>{product}</strong>
        {subtitle ? <small>{subtitle}</small> : null}
      </div>
      {trailing || (
        <button className="native-profile-button" type="button" onClick={onProfile} aria-label={tx("Abrir perfil", "Open profile", language)}>
          <span>{avatar || <MoreHorizontal size={23} />}</span>
        </button>
      )}
    </header>
  );
}
