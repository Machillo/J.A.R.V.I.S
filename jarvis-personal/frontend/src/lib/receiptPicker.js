import { Capacitor } from "@capacitor/core";
import { FilePicker } from "@capawesome/capacitor-file-picker";

const MAX_RECEIPT_BYTES = 5 * 1024 * 1024;
const ALLOWED_RECEIPT_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "application/pdf",
]);

export const hasNativeReceiptPicker = Capacitor.isNativePlatform();

const validateReceipt = (file) => {
  if (!file) return null;
  if (file.size > MAX_RECEIPT_BYTES) throw new Error("El comprobante no puede superar 5 MB.");
  if (file.type && !ALLOWED_RECEIPT_TYPES.has(file.type)) {
    throw new Error("Usá una imagen JPG, PNG, WEBP o un archivo PDF.");
  }
  return file;
};

export const receiptFromWebInput = (input) => validateReceipt(input?.files?.item(0) || null);

export async function pickNativeReceipt() {
  const result = await FilePicker.pickFiles({
    types: ["image/jpeg", "image/png", "image/webp", "application/pdf"],
    limit: 1,
  });
  const picked = result.files?.[0];
  if (!picked) return null;

  const blob = picked.blob || (picked.webPath
    ? await fetch(picked.webPath).then((response) => {
      if (!response.ok) throw new Error("Android no permitió leer el comprobante seleccionado.");
      return response.blob();
    })
    : null);
  if (!blob) throw new Error("No pudimos leer el comprobante seleccionado.");

  return validateReceipt(new File([blob], picked.name || "comprobante", {
    type: picked.mimeType || blob.type || "application/octet-stream",
    lastModified: picked.modifiedAt || Date.now(),
  }));
}
