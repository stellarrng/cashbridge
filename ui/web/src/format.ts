// Formatting only. Nothing here derives a financial value; it renders numbers the backend already computed.

const grouped = (digits: number) =>
  new Intl.NumberFormat("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const WHOLE = grouped(0);
const CENTS = grouped(2);
const ONE = grouped(1);

export const usd = (value: number | null | undefined, cents = false): string =>
  value === null || value === undefined ? "n/a" : `USD ${(cents ? CENTS : WHOLE).format(value)}`;

export const amount = (value: number | null | undefined, cents = false): string =>
  value === null || value === undefined ? "n/a" : (cents ? CENTS : WHOLE).format(value);

export const vnd = (value: number): string => `VND ${WHOLE.format(value)}`;

export const pct = (value: number | null | undefined): string =>
  value === null || value === undefined ? "n/a" : `${ONE.format(value)}%`;

export const days = (value: number): string => `${ONE.format(value)}`;

export const shortDate = (iso: string): string => {
  const [year, month, day] = iso.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(day)} ${names[Number(month) - 1]} ${year}`;
};

export const dayMonth = (iso: string): string => shortDate(iso).split(" ").slice(0, 2).join(" ");

export const head = (hash: string, size = 10): string => `${hash.slice(0, size)}…`;

export const label = (code: string): string =>
  code.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
