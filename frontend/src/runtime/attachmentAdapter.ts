import type {
  AttachmentAdapter,
  CompleteAttachment,
  PendingAttachment,
} from "@assistant-ui/react";

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
    const contentType = _resolveContentType(file);
    return {
      id: crypto.randomUUID(),
      type: _attachmentType(contentType),
      name: file.name,
      contentType,
      file,
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
