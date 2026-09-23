import { LEGAL_URLS, openLegalDocument } from "../lib/legalLinks";

export default function LegalLink({ kind, className, children }) {
  return <a className={className} href={LEGAL_URLS[kind]} target="_blank" rel="noopener noreferrer" onClick={(event) => openLegalDocument(event, kind)}>{children}</a>;
}
