import { useMemo, useState } from "react";
import { ImageModal } from "@/modals/ImageModal";
import type { ContentBlock } from "@/types/api";

interface Base64ImageProps {
  block: ContentBlock;
  alt?: string;
  className?: string;
}

export function Base64Image({ block, alt = "Image", className }: Base64ImageProps) {
  const [fullOpen, setFullOpen] = useState(false);
  // Screenshots run to hundreds of KB of base64; rebuilding the data URL on
  // every render reallocates that string and hands <img> a new src each time.
  const src = useMemo(
    () => (block.source ? `data:${block.source.media_type};base64,${block.source.data}` : null),
    [block.source],
  );
  if (!src) return null;
  return (
    <>
      <img
        src={src}
        alt={alt}
        className={className}
        onClick={(e) => { e.stopPropagation(); setFullOpen(true); }}
      />
      {fullOpen && <ImageModal src={src} alt={alt} onClose={() => setFullOpen(false)} />}
    </>
  );
}
