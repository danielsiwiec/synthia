import type {
  AttachmentAdapter,
  CompleteAttachment,
  PendingAttachment,
} from "@assistant-ui/react";

const MAX_BYTES = 10 * 1024 * 1024;
const MAX_IMAGE_EDGE = 1568;
const _IMAGE_QUALITY = 0.85;
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
    const { heicTo } = await import("heic-to");
    const blob = await heicTo({ blob: file, type: "image/jpeg", quality: 0.9 });
    const name = file.name.replace(/\.(heic|heif)$/i, "") + ".jpg";
    return new File([blob], name, { type: "image/jpeg" });
  } catch (error) {
    console.error("HEIC conversion failed, sending original:", error);
    return file;
  }
}

async function _downscaleImage(file: File): Promise<File> {
  try {
    const bitmap = await createImageBitmap(file);
    const longEdge = Math.max(bitmap.width, bitmap.height);
    if (longEdge <= MAX_IMAGE_EDGE) {
      bitmap.close();
      return file;
    }
    const scale = MAX_IMAGE_EDGE / longEdge;
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      bitmap.close();
      return file;
    }
    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", _IMAGE_QUALITY),
    );
    if (!blob) return file;
    const name = file.name.replace(/\.[^./]+$/, "") + ".jpg";
    return new File([blob], name, { type: "image/jpeg" });
  } catch (error) {
    console.error("Image downscale failed, sending original:", error);
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
    let resolved = _isHeic(file) ? await _convertHeic(file) : file;
    if (_attachmentType(_resolveContentType(resolved)) === "image") {
      resolved = await _downscaleImage(resolved);
    }
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
