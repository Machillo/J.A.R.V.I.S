import PremiumStrategy from "../../pages/PremiumStrategy";
import {
  getVipDebtAdvisory,
  getVipDebtStrategies,
  getVipAguinaldo,
  getVipSalvavidas,
  getVipStrategyDashboard,
  updateVipSalvavidas,
} from "../services/jarvisApi";

const finvaStrategyApi = {
  getStrategyDashboard: getVipStrategyDashboard,
  getDebtAdvisory: getVipDebtAdvisory,
  getDebtStrategies: getVipDebtStrategies,
  getSalvavidas: getVipSalvavidas,
  updateSalvavidas: updateVipSalvavidas,
  getAguinaldo: getVipAguinaldo,
};

export default function VipStrategy() {
  return <PremiumStrategy api={finvaStrategyApi} brandName="FINVA" />;
}
