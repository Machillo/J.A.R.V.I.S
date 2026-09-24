// Pure bank identification (no assets, testable in Node): code or name -> known bank.
// Order matters for free text: "banco nacional de costa rica" must win over
// "banco de costa rica". Codes are exact; text patterns avoid bare short codes.
export const BANK_IDENTITIES = [
  { id: "bac", name: "BAC Credomatic", short: "BAC", codes: ["bac", "baccredomatic", "credomatic"], text: /\bbac\b|credomatic/ },
  { id: "multimoney", name: "MultiMoney", short: "MM", codes: ["multimoney", "mm"], text: /multi ?money/ },
  { id: "bn", name: "Banco Nacional", short: "BN", codes: ["bn", "bncr", "banconacional", "banconacionaldecostarica"], text: /banco nacional|\bbncr\b/ },
  { id: "bcr", name: "Banco de Costa Rica", short: "BCR", codes: ["bcr", "bancodecostarica", "bancobcr"], text: /banco de costa rica|\bbancobcr\b|\bbcr\b/ },
  { id: "popular", name: "Banco Popular", short: "BP", codes: ["popular", "bancopopular", "bp", "bpdc"], text: /banco popular|bancopopular/ },
  { id: "davibank", name: "Davibank", short: "DB", codes: ["davibank", "scotiabank"], text: /davibank|scotiabank/ },
  { id: "davivienda", name: "Davivienda", short: "DV", codes: ["davivienda"], text: /davivienda/ },
  { id: "promerica", name: "Promerica", short: "PR", codes: ["promerica", "bancopromerica"], text: /promerica/ },
];

const plain = (value) => String(value || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const compact = (value) => plain(value).replace(/[^a-z0-9]/g, "");

export function bankInitials(name) {
  const words = plain(name).replace(/[^a-z0-9 ]/g, " ").split(/\s+/)
    .filter((word) => word && !["banco", "de", "del", "la", "el"].includes(word));
  return (words.length > 1 ? words.slice(0, 2).map((word) => word[0]).join("") : (words[0] || "?").slice(0, 3)).toUpperCase();
}

// Exact institution code or bank name (e.g. account_balances.institution_code, candidate.bank).
export function identifyBank(identifier) {
  const key = compact(identifier);
  if (!key || key === "unknown") return null;
  return BANK_IDENTITIES.find((bank) => bank.codes.includes(key) || compact(bank.name) === key)
    || BANK_IDENTITIES.find((bank) => bank.text.test(plain(identifier)))
    || null;
}

// Free text such as an email sender or subject.
export function identifyBankInText(text) {
  const value = plain(text);
  return value ? BANK_IDENTITIES.find((bank) => bank.text.test(value)) || null : null;
}

// Always displayable: a known bank, or initials for an unknown institution.
export function describeBank(identifier, fallbackName = "") {
  const bank = identifyBank(identifier) || identifyBank(fallbackName);
  if (bank) return bank;
  const name = String(fallbackName || identifier || "").trim();
  return { id: compact(name) || "unknown", name, short: name ? bankInitials(name) : "?" };
}
