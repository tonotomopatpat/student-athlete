import type { Material } from "../lib/api";
import { Chip } from "./ui";

export function MaterialStatus({ material }: { material: Material }) {
  if (material.kind === "link") return null;
  const status = material.extraction_status;
  switch (status) {
    case "ok":
      return <Chip tone="done">Text read</Chip>;
    case "needs_review":
      return <Chip tone="warn">No text found</Chip>;
    case "failed":
      return <Chip tone="warn">Could not read</Chip>;
    case "pending":
      return <Chip>{material.mime_type?.startsWith("image/") ? "Image, not read yet" : "Waiting"}</Chip>;
    default: {
      const unhandled: never = status;
      return unhandled;
    }
  }
}
