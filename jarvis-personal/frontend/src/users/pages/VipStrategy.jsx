import { useEffect, useState } from "react";
import PremiumStrategy from "../../pages/PremiumStrategy";
import StrategyOptionalActions from "../components/StrategyOptionalActions";
import {
  getVipDebtAdvisory,
  getVipAguinaldo,
  getVipSalvavidas,
  getStrategyVip,
  getVipStrategyDashboard,
  updateVipSalvavidas,
} from "../services/jarvisApi";

const finvaStrategyApi = {
  getStrategyDashboard: getVipStrategyDashboard,
  getDebtAdvisory: getVipDebtAdvisory,
  getSalvavidas: getVipSalvavidas,
  updateSalvavidas: updateVipSalvavidas,
  getAguinaldo: getVipAguinaldo,
};

export default function VipStrategy() {
  // The VIP dashboard comes from a different engine; the optional P2 suggestion comes
  // from the Users strategy engine and is shown apart from the monthly plan.
  const [optionalActions, setOptionalActions] = useState([]);
  useEffect(() => {
    let active = true;
    getStrategyVip().then((data) => { if (active) setOptionalActions(data?.optional_actions || []); }).catch(() => {});
    return () => { active = false; };
  }, []);
  return (
    <>
      <StrategyOptionalActions actions={optionalActions} />
      <PremiumStrategy api={finvaStrategyApi} brandName="DINCR" />
    </>
  );
}
