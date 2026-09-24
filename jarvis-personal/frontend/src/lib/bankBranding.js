// Central bank branding: institution code or name -> name, initials and logo.
// Presentation only (no data, no Owner tools). A bank without an asset keeps its
// initials, so a missing logo never breaks a screen.
import bacLogo from "../assets/institutions/bac.svg";
import bcrLogo from "../assets/institutions/bcr.png";
import bnLogo from "../assets/institutions/bn.png";
import davibankLogo from "../assets/institutions/davibank.png";
import daviviendaLogo from "../assets/institutions/davivienda.png";
import multimoneyLogo from "../assets/institutions/multimoney.png";
import popularLogo from "../assets/institutions/popular.png";
import promericaLogo from "../assets/institutions/promerica.png";
import { BANK_IDENTITIES, describeBank, identifyBank, identifyBankInText } from "./bankIdentity";

const LOGOS = {
  bac: bacLogo, bcr: bcrLogo, bn: bnLogo, davibank: davibankLogo, davivienda: daviviendaLogo,
  multimoney: multimoneyLogo, popular: popularLogo, promerica: promericaLogo,
};

const withLogo = (bank) => bank && { ...bank, logo: LOGOS[bank.id] || null };

export const BANKS = BANK_IDENTITIES.map(withLogo);
export const resolveBank = (identifier) => withLogo(identifyBank(identifier));
export const findBankInText = (text) => withLogo(identifyBankInText(text));
export const bankBranding = (identifier, fallbackName = "") => withLogo(describeBank(identifier, fallbackName));
