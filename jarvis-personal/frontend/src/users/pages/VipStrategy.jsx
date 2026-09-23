import PremiumStrategy from "../../pages/PremiumStrategy";
import {
  getVipDebtAdvisory,
  getVipAguinaldo,
  getVipSalvavidas,
  getVipStrategyDashboard,
  updateVipSalvavidas,
} from "../services/jarvisApi";

const dincrStrategyApi = {
  getStrategyDashboard: getVipStrategyDashboard,
  getDebtAdvisory: getVipDebtAdvisory,
  getSalvavidas: getVipSalvavidas,
  updateSalvavidas: updateVipSalvavidas,
  getAguinaldo: getVipAguinaldo,
};

export default function VipStrategy() {
  return <PremiumStrategy api={dincrStrategyApi} brandName="DINCR" />;
}
