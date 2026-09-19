import { MoreHorizontal } from "lucide-react";
import { deviceLanguage, tx } from "../../lib/locale";

export default function NativeProductHeader({ product, subtitle, eyebrow, title, avatar, onProfile, trailing, variant = "" }) {
  const language = deviceLanguage();
  return (
    <header className={`native-product-header ${variant ? `native-product-header--${variant}` : ""}`.trim()}>
      <div className="native-product-title">
        {eyebrow ? <small>{eyebrow}</small> : null}
        <strong>{title || product}</strong>
        {!eyebrow && subtitle ? <small>{subtitle}</small> : null}
      </div>
      {trailing || (
        <button className="native-profile-button" type="button" onClick={onProfile} aria-label={tx("Abrir perfil", "Open profile", language)}>
          <span>{avatar || <MoreHorizontal size={23} />}</span>
        </button>
      )}
    </header>
  );
}
