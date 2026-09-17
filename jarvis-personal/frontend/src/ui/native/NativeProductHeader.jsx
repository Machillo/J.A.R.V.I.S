import { MoreHorizontal } from "lucide-react";

export default function NativeProductHeader({ product, subtitle, avatar, onProfile, trailing }) {
  return (
    <header className="native-product-header">
      <div className="native-product-title">
        <strong>{product}</strong>
        {subtitle ? <small>{subtitle}</small> : null}
      </div>
      {trailing || (
        <button className="native-profile-button" type="button" onClick={onProfile} aria-label="Abrir perfil">
          <span>{avatar || <MoreHorizontal size={23} />}</span>
        </button>
      )}
    </header>
  );
}
