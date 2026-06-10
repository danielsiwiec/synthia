import type {
  AttachmentAdapter,
  CompleteAttachment,
  PendingAttachment,
} from "@assistant-ui/react";
import heic2any from "heic2any";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/*,.heic,.heif,application/pdf,text/*,.csv,.json,.md";

const _EXTENSION_MIME_TYPES: Record<string, string> = {
  heic: "image/heic",
  heif: "image/heif",
};

function _resolveContentType(file: File): string {
  if (file.type) return file.type;
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  return _EXTENSION_MIME_TYPES[ext] ?? "";
}

function _isHeic(file: File): boolean {
  const contentType = _resolveContentType(file);
  return contentType === "image/heic" || contentType === "image/heif";
}

async function _convertHeic(file: File): Promise<File> {
  try {
    const converted = await heic2any({ blob: file, toType: "image/jpeg", quality: 0.9 });
    const blob = Array.isArray(converted) ? converted[0] : converted;
    const name = file.name.replace(/\.(heic|heif)$/i, "") + ".jpg";
    return new File([blob], name, { type: "image/jpeg" });
  } catch (error) {
    console.error("HEIC conversion failed, sending original:", error);
    return file;
  }
}

function _readDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error ?? new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}

function _attachmentType(contentType: string): "image" | "document" | "file" {
  if (contentType.startsWith("image/")) return "image";
  if (contentType === "application/pdf" || contentType.startsWith("text/")) return "document";
  return "file";
}

export const attachmentAdapter: AttachmentAdapter = {
  accept: ACCEPT,
  async add({ file }): Promise<PendingAttachment> {
    if (file.size > MAX_BYTES) {
      throw new Error(`"${file.name}" exceeds the ${MAX_BYTES / 1024 / 1024}MB limit`);
    }
    const resolved = _isHeic(file) ? await _convertHeic(file) : file;
    const contentType = _resolveContentType(resolved);
    return {
      id: crypto.randomUUID(),
      type: _attachmentType(contentType),
      name: resolved.name,
      contentType,
      file: resolved,
      status: { type: "requires-action", reason: "composer-send" },
    };
  },
  async send(attachment): Promise<CompleteAttachment> {
    const dataUrl = await _readDataUrl(attachment.file);
    const part =
      attachment.type === "image"
        ? { type: "image" as const, image: dataUrl, filename: attachment.name }
        : {
            type: "file" as const,
            data: dataUrl,
            mimeType: attachment.contentType || "application/octet-stream",
            filename: attachment.name,
          };
    return { ...attachment, status: { type: "complete" }, content: [part] };
  },
  async remove() {},
};
