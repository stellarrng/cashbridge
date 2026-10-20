import { useEffect, useState } from "react";

interface Props {
  /** What the code opens. */
  text: string;
  label: string;
}

/**
 * A QR code drawn as one SVG path (no external service, nothing is sent anywhere). Always dark on white so any
 * phone camera can read it, in both themes. The encoder loads on demand so the landing page stays light.
 */
export function QrCode({ text, label }: Props) {
  const [matrix, setMatrix] = useState<{ size: number; path: string } | null>(null);

  useEffect(() => {
    let alive = true;
    import("qrcode").then((QR) => {
      if (!alive) return;
      const qr = QR.create(text, { errorCorrectionLevel: "M" });
      const n = qr.modules.size;
      let path = "";
      for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (qr.modules.get(r, c)) path += `M${c} ${r}h1v1h-1z`;
      setMatrix({ size: n, path });
    });
    return () => {
      alive = false;
    };
  }, [text]);

  const quiet = 2;
  return (
    <div className="qr" role="img" aria-label={label}>
      {matrix ? (
        <svg viewBox={`${-quiet} ${-quiet} ${matrix.size + quiet * 2} ${matrix.size + quiet * 2}`} shapeRendering="crispEdges" aria-hidden="true">
          <rect x={-quiet} y={-quiet} width={matrix.size + quiet * 2} height={matrix.size + quiet * 2} fill="#ffffff" />
          <path d={matrix.path} fill="#1d2125" />
        </svg>
      ) : null}
    </div>
  );
}
