import { post } from "@/shared/api/client";

export const askCfo = (text: string) => post<unknown>("/api/ask_cfo", { text });
