import { useEffect, useState } from "react";

export interface HashRoute {
  /** First segment: the screen ("overview", "core", "case"...). */
  name: string;
  /** Second segment, if any ("core/decide" -> "decide", "case/PACK-1" -> "PACK-1"). */
  arg: string | undefined;
}

function parse(): HashRoute {
  const [name = "", arg] = (window.location.hash || "").slice(1).split("/");
  return { name, arg };
}

/** Screens are addressed by the URL hash (/app#funding), so a static host needs no rewrite rules. */
export function useHashRoute(): HashRoute {
  const [route, setRoute] = useState<HashRoute>(parse);
  useEffect(() => {
    const onChange = () => setRoute(parse());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
