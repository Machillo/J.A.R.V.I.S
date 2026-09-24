import { useState } from "react";

// Real logo when DINCR has the asset; initials when the bank is unknown or the image fails.
export default function BankLogo({ bank, className = "" }) {
  const [failed, setFailed] = useState(false);
  const showLogo = bank?.logo && !failed;
  return <span className={`bank-logo bank-logo--${bank?.id || "unknown"} ${showLogo ? "bank-logo--image" : ""} ${className}`.trim()} aria-hidden="true">
    {showLogo ? <img src={bank.logo} alt="" onError={() => setFailed(true)}/> : bank?.short || "?"}
  </span>;
}
