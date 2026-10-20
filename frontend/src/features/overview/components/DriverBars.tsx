import type { Attribution } from "@/entities/forecast";
import { HBars } from "@/shared/charts";
import { usd, usd2 } from "@/shared/lib/format";

/** What pushes the first negative week below zero, largest first. */
export function DriverBars({ drivers }: { drivers: Attribution[] }) {
  const top = drivers.slice().sort((a, b) => b.amount_usd - a.amount_usd).slice(0, 6);
  return (
    <HBars
      items={top.map((a) => ({
        label: a.driver.replace(" (SYNTHETIC)", "").replace(/ is likely late: (\d+)% chance of on-time payment/, " late ($1% on time)"),
        value: a.amount_usd,
        display: usd(a.amount_usd),
        cls: a.amount_usd >= 0 ? "cb-neg" : "cb-good",
        tip: `${a.driver}\n${usd2(a.amount_usd)}\n${a.source_ref}`,
      }))}
    />
  );
}
